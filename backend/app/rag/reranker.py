import hashlib
import json
import logging
import math
from functools import lru_cache
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any

from app.core.config import Settings
from app.rag.repository import RetrievedChunk

BGE_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
BGE_ARTIFACT_HASHES = {
    "model.safetensors": "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286",
    "tokenizer.json": "69564b696052886ed0ac63fa393e928384e0f8caada38c1f4864a9bfbf379c15",
}
logger = logging.getLogger(__name__)


class RerankerDeviceError(RuntimeError):
    """A configured local CUDA device is unavailable; vector fallback remains valid."""


class LocalReranker:
    def __init__(
        self, model_path: str, revision: str, device: str, batch_size: int, max_length: int
    ) -> None:
        self._path = Path(model_path)
        self._revision = revision
        self._device = device
        self._batch_size = batch_size
        self._max_length = max_length
        self._model: Any = None
        self._unavailable = False
        self._lock = Lock()

    def _load(self) -> Any:
        if self._revision != BGE_REVISION:
            raise ValueError("Unverified reranker revision")
        required = ("config.json", "tokenizer.json", "model.safetensors")
        if not self._path.is_dir() or any(not (self._path / f).is_file() for f in required):
            raise FileNotFoundError("Local reranker artifact is incomplete")
        config = json.loads((self._path / "config.json").read_text(encoding="utf-8"))
        if config.get("architectures") != ["XLMRobertaForSequenceClassification"]:
            raise ValueError("Unexpected local model architecture")
        for name, expected in BGE_ARTIFACT_HASHES.items():
            with (self._path / name).open("rb") as artifact:
                if hashlib.file_digest(artifact, "sha256").hexdigest() != expected:
                    raise ValueError("Local model artifact integrity failed")
        if self._device in {"cuda", "cuda:0"}:
            import torch

            if torch.version.cuda is None or not torch.cuda.is_available():
                raise RerankerDeviceError("Configured CUDA device is unavailable")
        from sentence_transformers import CrossEncoder

        return CrossEncoder(
            str(self._path),
            revision=self._revision,
            device=self._device,
            max_length=self._max_length,
            local_files_only=True,
            trust_remote_code=False,
        )

    def rerank(
        self, question: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not 1 <= top_n <= 20 or len(candidates) > 50:
            raise ValueError("Reranking bounds exceeded")
        if not candidates:
            return []
        started = perf_counter()
        with self._lock:
            if self._unavailable:
                return candidates[:top_n]
            try:
                if self._model is None:
                    self._model = self._load()
                scores = self._model.predict(
                    [(question[:8000], chunk.content[:24000]) for chunk in candidates],
                    batch_size=self._batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                if len(scores) != len(candidates) or any(
                    not math.isfinite(float(score)) for score in scores
                ):
                    raise ValueError("Invalid local reranker scores")
                order = sorted(range(len(candidates)), key=lambda i: (-float(scores[i]), i))
                ranked = [candidates[i] for i in order[:top_n]]
            except Exception as exc:
                # Keep the original authorized objects on failure; never synthesize evidence.
                self._unavailable = True
                self._model = None
                category = (
                    "cuda_unavailable"
                    if isinstance(exc, RerankerDeviceError)
                    else "cuda_oom"
                    if self._device.startswith("cuda") and type(exc).__name__ == "OutOfMemoryError"
                    else "model_unavailable"
                )
                logger.warning(
                    "Local reranker unavailable device=%s failure=%s (%s); vector fallback",
                    self._device,
                    category,
                    type(exc).__name__,
                )
                return candidates[:top_n]
        logger.info(
            "Local rerank candidates=%d selected=%d elapsed_ms=%d",
            len(candidates),
            len(ranked),
            (perf_counter() - started) * 1000,
        )
        return ranked


@lru_cache(maxsize=1)
def _shared_reranker(
    path: str, revision: str, device: str, batch_size: int, max_length: int
) -> LocalReranker:
    return LocalReranker(path, revision, device, batch_size, max_length)


def build_reranker(settings: Settings) -> LocalReranker | None:
    if not settings.rag_reranker_path:
        return None
    return _shared_reranker(
        settings.rag_reranker_path,
        settings.rag_reranker_revision,
        settings.rag_reranker_device,
        settings.rag_reranker_batch_size,
        settings.rag_reranker_max_length,
    )
