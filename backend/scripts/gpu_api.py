"""GPU development entrypoint: warm the same per-process model used by API factories."""

import logging
import os

from fastapi import FastAPI

from app.core.config import get_settings
from app.main import app
from app.rag.repository import RetrievedChunk
from app.rag.reranker import build_reranker

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.app_environment != "development" or settings.rag_reranker_device != "cuda:0":
        raise ValueError("GPU entrypoint requires explicit CUDA development configuration")
    ranker = build_reranker(settings)
    if ranker is None:
        raise ValueError("GPU development requires a verified local model path")
    candidates = [
        RetrievedChunk(1, "synthetic.md", "Warmup", "Delivery completes within two days.", 0.1),
        RetrievedChunk(2, "synthetic.md", "Warmup", "Oranges are citrus fruit.", 0.2),
    ]
    ranked = ranker.rerank("How long does delivery take?", candidates, 1)
    if ranker._unavailable:
        logger.warning("GPU development warmup unavailable pid=%d; vector fallback", os.getpid())
    else:
        import torch

        logger.info(
            "GPU development warmup pid=%d device=%s dtype=%s shared=%s selected=%d "
            "allocated_mib=%.1f reserved_mib=%.1f",
            os.getpid(),
            ranker._model.device,
            next(ranker._model.model.parameters()).dtype,
            build_reranker(settings) is ranker,
            ranked[0].chunk_id,
            torch.cuda.memory_allocated() / 2**20,
            torch.cuda.memory_reserved() / 2**20,
        )
    return app
