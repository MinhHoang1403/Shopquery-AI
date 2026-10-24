"""Failure classes cross real SDK serializers without paid provider requests."""

import json
from unittest.mock import Mock

import httpx
import httpx2
import pytest

from app.api.routes import _chat_error
from app.core.diagnostics import diagnostic_request, diagnostic_stage, record_facts
from app.core.errors import ChatTurnError, ErrorContext, ModelResponseError, ProviderError
from app.routing.router import RouteDecision
from app.text_to_sql.query_plan import PlanDecision
from tests.test_gemini import _build_harness
from tests.test_plan_providers import response
from tests.test_providers import harness


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize(
    "status,category",
    [
        (400, "request_rejected"),
        (401, "authentication_or_permission"),
        (403, "authentication_or_permission"),
        (408, "timeout"),
        (429, "quota_or_rate_limit"),
        (503, "transient_unavailable"),
    ],
)
def test_http_error_preserves_status_category_one_attempt_and_safe_history(
    monkeypatch,
    caplog,
    provider,
    status,
    category,
):
    payload = {"error": {"code": status, "message": "PRIVATE-secret-body"}}
    if provider == "knowledge":
        gateway, calls = harness(monkeypatch, [httpx2.Response(status, json=payload)])
    else:
        run = _build_harness(monkeypatch, [httpx.Response(status, json=payload)], attempts=1)
        gateway, calls = run.gateway, run.calls
    try:
        with diagnostic_request() as trace:
            record_facts(route="HYBRID")
            with (
                pytest.raises(ModelResponseError) as caught,
                diagnostic_stage("generator_unsupported"),
            ):
                gateway.generate_structured("PRIVATE-question", RouteDecision)
            result = _chat_error(ChatTurnError(caught.value, "gemini"))
    finally:
        gateway.close()
    meta = result.error_context
    assert (meta.http_status, meta.error_category, meta.attempt) == (status, category, 1)
    assert meta.origin_stage == "generator_unsupported"
    assert meta.correlation_id == trace.correlation_id
    assert meta.attempted_route == "HYBRID" and result.route is None
    assert result.used_model is None and result.requested_model == "gemini"
    assert len(calls) == 1
    assert "PRIVATE" not in result.model_dump_json() + str(trace.events) + caplog.text
    assert "bằng dữ liệu hiện có" not in result.answer


def wire(**updates):
    return dict(
        outcome="query",
        reason="",
        source="t0",
        fields=[{"reference": "e0", "alias": "n"}],
        expressions=[
            {"operation": "row_count", "arguments": [], "value": "", "value_type": "none"}
        ],
        filters=[],
        group_by=[],
        sort=[],
        limit=0,
        relationships=[],
        where="",
        having="",
        **updates,
    )


@pytest.mark.parametrize(
    "kind,phase,category",
    [
        ("json", "json_decode", "invalid_json"),
        ("wire", "wire_validation", "wire_validation"),
        ("literal", "domain_conversion", "contract_conversion"),
        ("references", "domain_conversion", "contract_conversion"),
    ],
)
def test_gemini_decode_wire_and_conversion_are_distinct(monkeypatch, kind, phase, category):
    payload = wire()
    if kind == "wire":
        payload["limit"] = "PRIVATE"
    if kind == "literal":
        payload["expressions"][0].update(operation="literal")
    if kind == "references":
        payload["expressions"][0].update(operation="sum", arguments=["e0"])
    text = "PRIVATE invalid json" if kind == "json" else json.dumps(payload)
    run = _build_harness(monkeypatch, [response("gemini", text)], attempts=1)
    try:
        with (
            diagnostic_request() as trace, pytest.raises(ModelResponseError) as caught,
            diagnostic_stage("generator_unsupported"),
        ):
            run.gateway.generate_structured("PRIVATE", PlanDecision)
    finally:
        run.close()
    meta = caught.value.error_context
    assert (meta.phase, meta.error_category) == (phase, category)
    assert meta.origin_stage == "generator_unsupported"
    assert len(run.calls) == 1
    assert "PRIVATE" not in meta.model_dump_json() + str(trace.events)
    if kind == "wire":
        assert meta.validation_location == ["limit"] and meta.validation_type == "int_type"


def test_sdk_failure_is_local_preparation_not_invalid_model_json(monkeypatch):
    run = _build_harness(monkeypatch, [], attempts=1)
    monkeypatch.setattr(
        run.gateway._client.models, "generate_content", Mock(side_effect=ValueError("PRIVATE"))
    )
    try:
        with pytest.raises(ProviderError) as caught:
            run.gateway.generate_structured("PRIVATE", PlanDecision)
        assert caught.value.error_context.phase == "request"
        assert caught.value.error_context.error_category == "sdk_preparation"
        assert caught.value.error_context.http_status is None
        assert run.calls == []
    finally:
        run.close()


def test_timeout_classification_and_no_hidden_sdk_retry(monkeypatch):
    gateway, calls = harness(monkeypatch, [httpx2.ReadTimeout("PRIVATE")])
    try:
        with pytest.raises(ProviderError) as caught:
            gateway.generate_structured("PRIVATE", RouteDecision)
        assert caught.value.error_context.error_category == "timeout"
        assert caught.value.error_context.attempt == 1
        assert len(calls) == 1
    finally:
        gateway.close()


def test_validation_locations_are_bounded_and_do_not_expose_extra_keys():
    meta = ErrorContext(validation_location=["fields", 20000, "PRIVATE"], validation_type="PRIVATE")
    assert meta.validation_location == ["fields", 1000, "<field>"]
    assert meta.validation_type == "validation_error"
    assert "PRIVATE" not in meta.model_dump_json()


def test_wire_validation_does_not_run_domain_conversion(monkeypatch):
    from app.text_to_sql.generation_contract import GenerationDecision

    convert = Mock(side_effect=AssertionError("conversion must happen separately"))
    monkeypatch.setattr(GenerationDecision, "decision", convert)
    GenerationDecision.model_validate(wire())
    convert.assert_not_called()
