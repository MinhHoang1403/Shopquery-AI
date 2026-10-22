import json
import sys
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.config import Settings
from app.core.errors import RetrievalError
from app.rag.pipeline import RagPipeline
from app.rag.repository import RetrievedChunk
from app.rag.reranker import BGE_REVISION, LocalReranker, build_reranker


def chunks():
    return [
        RetrievedChunk(i, f"source-{i}.md", "Policy", f"Content {i}", i / 10) for i in (1, 2, 3)
    ]


def reranker():
    return LocalReranker("missing", BGE_REVISION, "cpu", 2, 512)


def test_local_model_is_loaded_once_and_preserves_original_objects(monkeypatch):
    model = Mock(predict=Mock(return_value=[0.2, 0.9, 0.3]))
    loader = Mock(return_value=model)
    subject = reranker()
    monkeypatch.setattr(subject, "_load", loader)
    candidates = chunks()
    for _ in range(2):
        ranked = subject.rerank("query", candidates, 2)
        assert ranked == [candidates[1], candidates[2]]
        assert ranked[0] is candidates[1]
    loader.assert_called_once()
    assert model.predict.call_args.kwargs["batch_size"] == 2


@pytest.mark.parametrize("scores", [[float("nan"), 1, 2], [1], [[1, 2], [3, 4], [5, 6]]])
def test_bad_scores_use_original_vector_order(monkeypatch, scores):
    subject = reranker()
    monkeypatch.setattr(subject, "_load", lambda: Mock(predict=Mock(return_value=scores)))
    candidates = chunks()
    assert subject.rerank("query", candidates, 2) == candidates[:2]
    assert subject._unavailable


def test_missing_model_fallback_does_not_retry_or_download(monkeypatch):
    subject = reranker()
    loader = Mock(side_effect=FileNotFoundError("private path"))
    monkeypatch.setattr(subject, "_load", loader)
    for _ in range(2):
        assert subject.rerank("query", chunks(), 2) == chunks()[:2]
    loader.assert_called_once()


def test_scope_is_applied_before_rerank_and_sources_are_unchanged():
    candidates = chunks()
    repository = Mock(retrieve=Mock(return_value=candidates))
    ranker = Mock(rerank=Mock(return_value=[candidates[2], candidates[0]]))
    pipeline = RagPipeline(Mock(), Mock(), repository, 17, ranker, 12, 2)
    assert pipeline.retrieve("question") == [candidates[2], candidates[0]]
    assert repository.retrieve.call_args.kwargs == {"top_k": 12, "dataset_id": 17}
    assert ranker.rerank.call_args.args == ("question", candidates, 2)


@pytest.mark.parametrize("mutate", [lambda c: replace(c, content="injected"), lambda c: c])
def test_unretrieved_or_duplicate_reranker_evidence_is_rejected(mutate):
    candidates = chunks()
    ranker = Mock(rerank=Mock(return_value=[mutate(candidates[0]), mutate(candidates[0])]))
    pipeline = RagPipeline(
        Mock(), Mock(), Mock(retrieve=Mock(return_value=candidates)), 17, ranker, 12, 2
    )
    with pytest.raises(RetrievalError):
        pipeline.retrieve("question")


def test_model_instance_is_shared_between_request_pipelines():
    settings = Settings(_env_file=None, rag_reranker_path="synthetic")
    assert build_reranker(settings) is build_reranker(settings)
    assert build_reranker(Settings(_env_file=None)) is None


def test_same_chunk_id_does_not_authorize_modified_content():
    candidates = chunks()
    modified = replace(candidates[0], content="Different workspace content")
    ranker = Mock(rerank=Mock(return_value=[modified]))
    pipeline = RagPipeline(
        Mock(), Mock(), Mock(retrieve=Mock(return_value=candidates)), 17, ranker, 12, 1
    )
    with pytest.raises(RetrievalError):
        pipeline.retrieve("question")


def test_missing_artifact_is_refused_before_library_import():
    with pytest.raises(FileNotFoundError):
        reranker()._load()


def test_unavailable_cuda_falls_back_once_without_cross_encoder_import(
    tmp_path, monkeypatch, caplog
):
    available = Mock(return_value=False)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            version=SimpleNamespace(cuda="13.0"), cuda=SimpleNamespace(is_available=available)
        ),
    )
    monkeypatch.setattr("app.rag.reranker.BGE_ARTIFACT_HASHES", {})
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["XLMRobertaForSequenceClassification"],
            }
        )
    )
    for name in ("tokenizer.json", "model.safetensors"):
        (tmp_path / name).write_bytes(b"synthetic")
    subject = LocalReranker(str(tmp_path), BGE_REVISION, "cuda:0", 2, 512)
    candidates = chunks()
    for _ in range(2):
        assert subject.rerank("question", candidates, 2) == candidates[:2]
    available.assert_called_once()
    assert subject._unavailable and subject._model is None
    assert "device=cuda:0 failure=cuda_unavailable" in caplog.text
    assert str(tmp_path) not in caplog.text


def test_cuda_oom_keeps_authorized_sources_and_logs_safe_failure(monkeypatch, caplog):
    class OutOfMemoryError(RuntimeError):
        pass

    loader = Mock(side_effect=OutOfMemoryError("private diagnostic detail"))
    subject = LocalReranker("synthetic", BGE_REVISION, "cuda:0", 2, 512)
    monkeypatch.setattr(subject, "_load", loader)
    candidates = chunks()
    for _ in range(2):
        ranked = subject.rerank("question", candidates, 2)
        assert ranked[0] is candidates[0] and ranked[1] is candidates[1]
    loader.assert_called_once()
    assert "failure=cuda_oom" in caplog.text
    assert "private diagnostic detail" not in caplog.text
