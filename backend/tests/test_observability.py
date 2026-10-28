"""Exercise the installed SDK and sanitized export without any provider/network calls."""

import json
from contextlib import contextmanager
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.ai.gemini import GeminiGateway
from app.ai.inetcloud import InetCloudGateway
from app.core import observability as telemetry
from app.core.config import Settings
from app.core.diagnostics import (
    STAGES,
    diagnostic_request,
    diagnostic_stage,
    record_facts,
    record_provider_tokens,
)
from app.core.errors import ProviderError


@pytest.fixture
def export(monkeypatch):
    from langfuse import Langfuse

    exporter = InMemorySpanExporter()
    monkeypatch.setenv("OTEL_BSP_MAX_QUEUE_SIZE", "64")
    monkeypatch.setenv("LANGFUSE_MEDIA_UPLOAD_ENABLED", "false")
    monkeypatch.setattr(
        "langfuse.Langfuse", lambda **kwargs: Langfuse(**kwargs, span_exporter=exporter)
    )
    settings = Settings(
        _env_file=None,
        langfuse_enabled=True,
        langfuse_public_key="pk-lf-test-" + uuid4().hex,
        langfuse_secret_key="synthetic-test-only",
        langfuse_base_url="http://127.0.0.1:1",
    )
    telemetry.configure(settings, STAGES)
    assert telemetry._client is not None

    def collect():
        telemetry._client.flush()  # Short-lived test only; never used in a turn.
        return exporter.get_finished_spans()

    yield exporter, collect
    telemetry.shutdown()


def metadata(span):
    prefix = "langfuse.observation.metadata."
    return {
        k.removeprefix(prefix): json.loads(v)
        for k, v in span.attributes.items()
        if k.startswith(prefix)
    }


def test_one_root_trace_correlates_nested_hybrid_sql_and_model_call(export):
    _, collect = export
    identifier = "a" * 32
    with diagnostic_request(identifier), diagnostic_request():
        record_facts(route="HYBRID", fallback_used=False)
        with diagnostic_stage("hybrid_pipeline"), diagnostic_stage("sql_pipeline"):
            with telemetry.provider_observation("knowledge", "knowledge", "generation"):
                record_provider_tokens({"input_tokens": 10, "output_tokens": 3, "total_tokens": 13})
            with diagnostic_stage("sql_execution"):
                record_facts(execution_reached=True, result_rows=5)
        record_facts(verification_status="verified_classification")
    spans = collect()
    assert len(spans) == 5
    assert {s.context.trace_id for s in spans} == {int(identifier, 16)}
    by_name = {s.name: s for s in spans}
    assert by_name["hybrid_pipeline"].parent.span_id == by_name["request"].context.span_id
    assert by_name["sql_pipeline"].parent.span_id == by_name["hybrid_pipeline"].context.span_id
    assert by_name["generation"].parent.span_id == by_name["sql_pipeline"].context.span_id
    assert sum(bool(s.attributes.get("langfuse.internal.as_root")) for s in spans) == 1
    assert metadata(by_name["request"])["verification_status"] == "verified_classification"
    assert "langfuse.observation.usage_details" not in by_name["request"].attributes


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_cached_and_reasoning_usage_are_not_added_to_sdk_totals(export, provider):
    _, collect = export
    usage = (
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_token_details": {"cache_read": 60},
            "output_token_details": {"reasoning": 5},
        }
        if provider == "knowledge"
        else SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=20,
            total_token_count=125,
            cached_content_token_count=60,
            thoughts_token_count=5,
        )
    )
    with diagnostic_request(), telemetry.provider_observation(provider, "knowledge", "generation"):
        record_provider_tokens(usage)
    generation = next(s for s in collect() if s.name == "generation")
    details = json.loads(generation.attributes["langfuse.observation.usage_details"])
    assert details == {"input": 100, "output": 20, "total": 120 if provider == "knowledge" else 125}
    assert metadata(generation)["cached_input_tokens"] == 60
    assert metadata(generation)["reasoning_tokens"] == 5
    assert metadata(generation)["usage_status"] == "measured"
    assert metadata(generation)["cost_status"] == "unknown"
    assert "langfuse.observation.cost_details" not in generation.attributes


@pytest.mark.parametrize("usage", [None, {}, {"input_tokens": 1}, {"input_tokens": -1}])
def test_missing_usage_is_unknown_or_partial_never_fabricated_zero(export, usage):
    _, collect = export
    with (
        diagnostic_request(),
        telemetry.provider_observation("knowledge", "knowledge", "generation"),
    ):
        record_provider_tokens(usage)
    span = next(s for s in collect() if s.name == "generation")
    expected = "partial" if usage == {"input_tokens": 1} else "unknown"
    assert metadata(span)["usage_status"] == expected
    if expected == "unknown":
        assert "langfuse.observation.usage_details" not in span.attributes


def test_privacy_masks_raw_io_metadata_identity_and_exception(export):
    _, collect = export
    with (
        pytest.raises(ValueError, match="SENSITIVE"),
        diagnostic_request(),
        diagnostic_stage("sql_execution"),
    ):
        span = telemetry._active.get()
        span.update(input="SENSITIVE question", output="SENSITIVE rows")
        span.update(
            metadata={
                "question": "SENSITIVE",
                "sql": "SELECT secret",
                "email": "private@example.test",
            }
        )
        raise ValueError("SENSITIVE database message")
    spans = collect()
    payload = str([(dict(s.attributes), s.events, s.status) for s in spans])
    for secret in ("SENSITIVE", "SELECT secret", "private@example.test"):
        assert secret not in payload
    assert all(not s.events for s in spans)
    assert all(s.status.description in (None, "internal_failure") for s in spans)
    assert any(metadata(s).get("status") == "failure" for s in spans)


def test_each_gateway_sdk_dispatch_has_one_observation_and_accurate_model(export):
    _, collect = export
    gemini = object.__new__(GeminiGateway)
    gemini._settings = Settings(_env_file=None)
    knowledge = object.__new__(InetCloudGateway)
    knowledge._settings = gemini._settings
    counts = {"input_tokens": 7, "output_tokens": 2, "total_tokens": 9}
    runnable = SimpleNamespace(invoke=lambda _: SimpleNamespace(usage_metadata=counts))
    with diagnostic_request():
        knowledge._invoke(runnable, "SENSITIVE")
        gemini._request("generation", lambda: SimpleNamespace(usage_metadata=None))
        gemini._request("embedding", lambda: SimpleNamespace(usage_metadata=None))
    spans = collect()
    calls = [s for s in spans if s.name != "request"]
    assert len(calls) == 3
    assert [s.attributes["langfuse.observation.model.name"] for s in calls] == [
        "knowledge",
        "gemini-3.5-flash-lite",
        "gemini-embedding-2",
    ]
    assert [s.attributes["langfuse.observation.type"] for s in calls] == [
        "generation",
        "generation",
        "embedding",
    ]
    assert "SENSITIVE" not in str([dict(s.attributes) for s in spans])


def test_provider_error_retains_unknown_consumption_and_safe_category(export):
    import httpx

    _, collect = export
    gateway = object.__new__(GeminiGateway)
    gateway._settings = Settings(_env_file=None)

    def timeout():
        raise httpx.ReadTimeout("SENSITIVE private endpoint")

    with pytest.raises(ProviderError), diagnostic_request():
        gateway._request("generation", timeout)
    call = next(s for s in collect() if s.name == "generation")
    assert metadata(call)["error_category"] == "timeout"
    assert metadata(call)["usage_status"] == "unknown"
    assert "SENSITIVE" not in str(dict(call.attributes))


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize(
    "status,category",
    [
        (401, "authentication_failed"),
        (403, "permission_denied"),
        (402, "payment_required"),
        (504, "timeout"),
    ],
)
def test_http_failure_exports_one_error_observation_with_exact_status(
    export, monkeypatch, provider, status, category
):
    import httpx
    import httpx2

    from app.routing.router import QueryRouter
    from tests.test_gemini import _build_harness
    from tests.test_providers import harness

    payload = {"error": {"code": status, "message": "SENSITIVE upstream error"}}
    if provider == "knowledge":
        gateway, calls = harness(monkeypatch, [httpx2.Response(status, json=payload)])
    else:
        run = _build_harness(monkeypatch, [httpx.Response(status, json=payload)], attempts=1)
        gateway, calls = run.gateway, run.calls
    _, collect = export
    try:
        with pytest.raises(ProviderError), diagnostic_request():
            QueryRouter(gateway).route("SENSITIVE question")
    finally:
        gateway.close()
    spans = collect()
    generations = [span for span in spans if span.name == "generation"]
    assert len(generations) == len(calls) == 1
    facts = metadata(generations[0])
    assert facts["http_status"] == status and facts["error_category"] == category
    assert facts["provider"] == provider and facts["usage_status"] == "unknown"
    assert generations[0].attributes["langfuse.observation.level"] == "ERROR"
    assert not any(span.name == "sql_execution" for span in spans)
    assert "SENSITIVE" not in str([dict(span.attributes) for span in spans])


def test_disabled_does_not_initialize_sdk_or_change_result(monkeypatch):
    def unexpected(**_):
        pytest.fail("SDK must not initialize when OFF")

    monkeypatch.setattr("langfuse.Langfuse", unexpected)
    telemetry.configure(Settings(_env_file=None, langfuse_enabled=False), STAGES)
    with diagnostic_request(), diagnostic_stage("sql_execution"):
        result = {"amount": "0.00"}
    assert result == {"amount": "0.00"}


@pytest.mark.parametrize("failure", ["initialization", "start", "end", "update"])
def test_sdk_failure_does_not_change_business_exception_or_output(monkeypatch, failure):
    class BrokenClient:
        @contextmanager
        def start_as_current_observation(self, **_):
            if failure == "start":
                raise RuntimeError("SENSITIVE start")
            yield SimpleNamespace(
                update=lambda **_: (_ for _ in ()).throw(RuntimeError("SENSITIVE update"))
            )
            if failure == "end":
                raise RuntimeError("SENSITIVE end")

    if failure == "initialization":
        monkeypatch.setattr(
            "langfuse.Langfuse", lambda **_: (_ for _ in ()).throw(RuntimeError("secret"))
        )
        telemetry.configure(
            Settings(
                _env_file=None,
                langfuse_enabled=True,
                langfuse_public_key="test",
                langfuse_secret_key="test",
                langfuse_base_url="http://127.0.0.1:1",
            ),
            STAGES,
        )
    else:
        monkeypatch.setattr(telemetry, "_client", BrokenClient())
    with diagnostic_request(), diagnostic_stage("sql_execution"):
        record_facts(result_rows=1)
    expected = ValueError("business failure")
    with (
        pytest.raises(ValueError) as caught,
        diagnostic_request(),
        diagnostic_stage("sql_execution"),
    ):
        raise expected
    assert caught.value is expected


def test_bounded_queue_drops_spans_without_waiting_for_export(export):
    exporter, _ = export
    processor = (
        telemetry._client._resources.tracer_provider._active_span_processor._span_processors[0]
    )
    assert processor._batch_processor._max_queue_size == 64
    entered, release, finished = Event(), Event(), Event()
    original = exporter.export

    def blocked(spans):
        entered.set()
        release.wait(5)
        return original(spans)

    exporter.export = blocked

    def produce():
        for _ in range(500):
            with telemetry.observation("routing"):
                pass
        finished.set()

    worker = Thread(target=produce)
    try:
        worker.start()
        assert entered.wait(2)
        assert finished.wait(2), "Turn must not wait on the blocked telemetry exporter"
        assert not release.is_set()
    finally:
        release.set()
        worker.join(5)


def test_allowlist_rejects_arbitrary_strings_and_invalid_counts():
    result = telemetry.safe_metadata(
        {
            "question": "secret",
            "route": "SELECT private",
            "result_rows": -1,
            "generation_calls": True,
            "correlation_id": "email@example.test",
            "model": "sk-secret",
            "sql_validated": True,
        }
    )
    assert result == {"sql_validated": True}


def test_untraced_dependency_does_not_export_orphan_span(export):
    _, collect = export
    with diagnostic_stage("authentication"):
        pass
    assert collect() == ()


def test_authentication_failure_has_safe_http_category(export):
    from fastapi import HTTPException

    _, collect = export
    with pytest.raises(HTTPException), diagnostic_request(), diagnostic_stage("authentication"):
        raise HTTPException(401, "SENSITIVE session detail")
    auth = next(s for s in collect() if s.name == "authentication")
    assert metadata(auth)["error_category"] == "authentication_or_permission"
    assert metadata(auth)["http_status"] == 401
    assert "SENSITIVE" not in str(dict(auth.attributes))


def test_request_summarizes_measured_usage_without_duplicate_usage_details(export):
    _, collect = export
    with diagnostic_request():
        record_facts(
            requested_model="inetcloud-knowledge",
            used_model="gemini",
            fallback_used=True,
            fallback_error_category="timeout",
            context_used=True,
        )
        with telemetry.provider_observation("knowledge", "knowledge", "generation"):
            record_provider_tokens({"input_tokens": 7, "output_tokens": 2, "total_tokens": 9})
        with telemetry.provider_observation("gemini", "gemini-3.5-flash-lite", "generation"):
            record_provider_tokens(
                SimpleNamespace(prompt_token_count=4, candidates_token_count=1, total_token_count=5)
            )
    root = next(s for s in collect() if s.name == "request")
    facts = metadata(root)
    assert (
        facts["request_input_tokens"],
        facts["request_output_tokens"],
        facts["request_total_tokens"],
    ) == (11, 3, 14)
    assert facts["requested_model"] == "inetcloud-knowledge"
    assert facts["used_model"] == "gemini"
    assert facts["fallback_used"] and facts["context_used"]
    assert "langfuse.observation.usage_details" not in root.attributes


def test_generation_contract_failure_preserves_measured_consumption(export):
    from pydantic import BaseModel

    from app.core.errors import StructuredResponseError

    class Draft(BaseModel):
        answer: str

    _, collect = export
    gateway = object.__new__(GeminiGateway)
    gateway._settings = Settings(_env_file=None)
    gateway._client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kw: SimpleNamespace(
                text='{"answer": []}',
                candidates=[],
                usage_metadata=SimpleNamespace(
                    prompt_token_count=11, candidates_token_count=3, total_token_count=14
                ),
            )
        )
    )
    with pytest.raises(StructuredResponseError), diagnostic_request():
        gateway.generate_structured("SENSITIVE", Draft)
    spans = collect()
    call = next(s for s in spans if s.name == "generation")
    contract = next(s for s in spans if s.name == "generation_contract")
    assert metadata(contract)["status"] == "failure"
    assert metadata(contract)["error_category"] == "wire_validation"
    assert json.loads(call.attributes["langfuse.observation.usage_details"])["total"] == 14
    assert call.parent.span_id == contract.context.span_id
    assert len([s for s in spans if s.name == "generation"]) == 1


def test_rag_retrieval_and_citations_export_counts_only(export):
    from app.rag.pipeline import RagAnswerDraft, RagPipeline

    _, collect = export
    chunk = SimpleNamespace(
        chunk_id=1, source_file="SENSITIVE", section_title="SENSITIVE", content="SENSITIVE"
    )
    pipeline = RagPipeline(
        SimpleNamespace(embed_query=lambda _: [0.1]),
        SimpleNamespace(
            generate_structured=lambda *args: RagAnswerDraft(answer="SENSITIVE", used_chunk_ids=[1])
        ),
        SimpleNamespace(retrieve=lambda *args, **kwargs: [chunk]),
    )
    with diagnostic_request():
        pipeline.run("SENSITIVE")
    spans = collect()
    root = next(s for s in spans if s.name == "request")
    assert metadata(root)["retrieved_chunks"] == 1
    assert metadata(root)["selected_chunks"] == 1
    assert metadata(root)["citation_count"] == 1
    assert "SENSITIVE" not in str([dict(s.attributes) for s in spans])


def test_embedding_characters_are_not_mislabeled_as_tokens(export):
    from google.genai import types

    _, collect = export
    gateway = object.__new__(GeminiGateway)
    gateway._settings = Settings(_env_file=None)
    response = types.EmbedContentResponse(
        metadata=types.EmbedContentMetadata(billable_character_count=20)
    )
    with diagnostic_request():
        gateway._request("embedding", lambda: response)
    call = next(s for s in collect() if s.name == "query_embedding")
    assert metadata(call)["billable_character_count"] == 20
    assert metadata(call)["usage_status"] == "unknown"
    assert "langfuse.observation.usage_details" not in call.attributes


def test_request_partial_usage_does_not_claim_total_consumption(export):
    from app.core.diagnostics import record_provider_call

    _, collect = export
    with diagnostic_request():
        record_provider_call("generation_calls")
        with telemetry.provider_observation("knowledge", "knowledge", "generation"):
            record_provider_tokens({"input_tokens": 7, "output_tokens": 2, "total_tokens": 9})
        record_provider_call("generation_calls")  # Failed dispatch without usage.
    root = next(s for s in collect() if s.name == "request")
    assert metadata(root)["usage_status"] == "partial"
    assert metadata(root)["request_total_tokens"] == 9  # Measured subtotal only.


def test_missing_credentials_disable_export_without_business_failure(monkeypatch):
    monkeypatch.setattr(
        "langfuse.Langfuse", lambda **kwargs: pytest.fail("SDK must not initialize")
    )
    telemetry.configure(
        Settings(
            _env_file=None,
            langfuse_enabled=True,
            langfuse_public_key=None,
            langfuse_secret_key=None,
        ),
        STAGES,
    )
    with diagnostic_request(), diagnostic_stage("sql_execution"):
        result = "unchanged"
    assert result == "unchanged"
    assert telemetry._client is None


def test_telemetry_only_stage_preserves_business_error_origin(export):
    _, collect = export
    error = ProviderError("SENSITIVE")
    before = error.error_context.model_dump()
    with (
        diagnostic_request(),
        pytest.raises(ProviderError),
        diagnostic_stage("generation_contract", annotate_error=False),
    ):
        raise error
    assert error.error_context.model_dump() == before
    stage = next(s for s in collect() if s.name == "generation_contract")
    assert metadata(stage)["status"] == "failure"
