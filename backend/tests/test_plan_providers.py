import json

import httpx
import httpx2
import pytest

from app.core.errors import (
    ModelResponseError,
    ProviderError,
    SqlUnsupportedError,
    SqlValidationError,
)
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.query_plan import PlanDecision
from tests.test_gemini import _build_harness
from tests.test_providers import completion, harness
from tests.test_workspace_prompts import tuition_context


def response(provider, text):
    if provider == "knowledge":
        return completion(text)
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {"parts": [{"text": text}], "role": "model"},
                    "finishReason": "STOP",
                }
            ]
        },
    )


def gateway_harness(monkeypatch, provider, responses):
    if provider == "knowledge":
        return harness(monkeypatch, responses)
    result = _build_harness(monkeypatch, responses)
    return result.gateway, result.calls


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_actual_adapter_serializes_plan_and_compiles(monkeypatch, provider):
    payload = {
        "plan": {
            "source": "t0",
            "fields": [
                {"alias": "rows", "aggregate": "row_count"},
            ],
        },
        "unsupported_reason": None,
    }
    gateway, calls = gateway_harness(
        monkeypatch, provider, [response(provider, json.dumps(payload))]
    )
    try:
        context = tuition_context()
        plan = QueryPlanner(gateway, "2026-10-01", context).generate("Count rows")
        assert (
            QueryCompiler(context).compile(plan).validated.count_metrics[0].output_alias == "rows"
        )
        assert len(calls) == 1
        body = json.loads(calls[0].content)
        serialized = json.dumps(body)
        assert "PlanDecision" in serialized and "expressions" in serialized
        assert "Must be null for field aggregate row_count" in serialized
        assert "aggregate is an operation applied to reference" in serialized
        assert 'sql"' not in json.dumps(PlanDecision.model_json_schema())
    finally:
        gateway.close()


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize("field_aggregate", [None, "sum", "row_count"])
def test_aggregate_expression_is_not_aggregated_again(monkeypatch, provider, field_aggregate):
    context = tuition_context()
    compiler = QueryCompiler(context)
    column = next(
        key
        for key, value in compiler.references.columns.items()
        if value == ("tuition_fixture", "da_dong")
    )
    payload = {
        "plan": {
            "source": "t0",
            "expressions": [
                {"operation": "sum", "arguments": [column]},
                {"operation": "row_count", "arguments": []},
            ],
            "fields": [
                {
                    "reference": "e1" if field_aggregate == "row_count" else "e0",
                    "alias": "metric",
                    "aggregate": field_aggregate,
                }
            ],
        }
    }
    gateway, calls = gateway_harness(
        monkeypatch, provider, [response(provider, json.dumps(payload))]
    )
    try:
        plan = QueryPlanner(gateway, "2026-10-01", context).generate("Tổng học phí đã đóng?")
        if field_aggregate is None:
            assert "SUM(" in compiler.compile(plan).validated.statement.upper()
        else:
            message = (
                "Invalid nested aggregate"
                if field_aggregate == "sum"
                else "Row count does not take a value column"
            )
            with pytest.raises(SqlValidationError, match=message):
                compiler.compile(plan)
        assert len(calls) == 1
    finally:
        gateway.close()


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"plan": None, "unsupported_reason": None},
        {"plan": {"source": "t0", "fields": []}},
        {"plan": None, "unsupported_reason": "unavailable", "sql": "SELECT 1"},
        {"plan": {"source": "t0", "fields": [{"alias": "x", "aggregate": "evil"}]}},
        {
            "plan": {
                "source": "t0",
                "fields": [{"alias": "x", "aggregate": "row_count"}],
                "expressions": [{"operation": "literal", "value": "1", "value_type": "NUMERIC"}]
                + [{"operation": "add", "arguments": [f"e{i}", f"e{i}"]} for i in range(8)],
            }
        },
        "invalid-json",
    ],
)
def test_invalid_provider_plans_fail_safely(monkeypatch, provider, payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    gateway, calls = gateway_harness(monkeypatch, provider, [response(provider, raw)] * 2)
    try:
        with pytest.raises((ProviderError, ModelResponseError)):
            QueryPlanner(gateway, "2026-10-01", tuition_context()).generate("Q")
        assert len(calls) == 1
    finally:
        gateway.close()


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_valid_unknown_reference_is_rejected_by_backend(monkeypatch, provider):
    raw = json.dumps(
        {
            "plan": {
                "source": "other_owner",
                "fields": [
                    {"alias": "n", "aggregate": "row_count"},
                ],
            }
        }
    )
    gateway, _ = gateway_harness(monkeypatch, provider, [response(provider, raw)])
    try:
        context = tuition_context()
        plan = QueryPlanner(gateway, "2026-10-01", context).generate("Q")
        with pytest.raises(SqlValidationError):
            QueryCompiler(context).compile(plan)
    finally:
        gateway.close()


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_unsupported_and_schema_rejection(monkeypatch, provider):
    raw = json.dumps({"plan": None, "unsupported_reason": "No verified relationship"})
    gateway, _ = gateway_harness(monkeypatch, provider, [response(provider, raw)])
    try:
        with pytest.raises(SqlUnsupportedError):
            QueryPlanner(gateway, "2026-10-01", tuition_context()).generate("Q")
    finally:
        gateway.close()
    monkeypatch.undo()
    error_response = (
        httpx2.Response(400, json={"error": {"message": "schema rejected"}})
        if provider == "knowledge"
        else httpx.Response(
            400,
            json={
                "error": {"code": 400, "message": "schema rejected", "status": "INVALID_ARGUMENT"},
            },
        )
    )
    gateway, calls = gateway_harness(monkeypatch, provider, [error_response])
    try:
        with pytest.raises((ProviderError, ModelResponseError)):
            QueryPlanner(gateway, "2026-10-01", tuition_context()).generate("Q")
        assert len(calls) == 1
    finally:
        gateway.close()
