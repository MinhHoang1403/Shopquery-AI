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
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        payload = None
    if isinstance(payload, dict) and "plan" in payload:
        plan = payload.get("plan") or {}
        plan = {
            **plan,
            "fields": [dict(field) for field in plan.get("fields", [])],
            "expressions": list(plan.get("expressions", [])),
        }
        for field in plan["fields"]:
            if field.get("aggregate") is None:
                field.pop("aggregate", None)
            elif field.get("aggregate") == "row_count" and field.get("reference") is None:
                field.pop("aggregate")
                field["reference"] = f"e{len(plan['expressions'])}"
                plan["expressions"].append({"operation": "row_count", "arguments": []})
        payload = {
            **{k: v for k, v in payload.items() if k not in {"plan", "unsupported_reason"}},
            "outcome": "query" if payload.get("plan") else "unsupported",
            "reason": payload.get("unsupported_reason") or "",
            "source": plan.get("source", ""),
            "grouping": plan.get("grouping", "entity"),
            "fields": plan.get("fields", []),
            "expressions": [
                {
                    **node,
                    "arguments": node.get("arguments", []),
                    "value": node.get("value") or "",
                    "value_type": node.get("value_type") or "none",
                }
                for node in plan.get("expressions", [])
            ],
            "filters": plan.get("filters", []),
            "group_by": plan.get("group_by", []),
            "sort": plan.get("sort", []),
            "limit": plan.get("limit") or 0,
            "relationships": plan.get("relationships", []),
            "where": plan.get("where") or "",
            "having": plan.get("having") or "",
        }
        text = json.dumps(payload)
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
            "expressions": [{"operation": "row_count", "arguments": []}],
            "fields": [
                {"reference": "e0", "alias": "rows"},
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
        assert "GenerationDecision" in serialized
        assert "expressions" in serialized
        assert "Fields only select values" in serialized
        assert 'sql"' not in json.dumps(PlanDecision.model_json_schema())
        if provider == "gemini":
            config = body["generationConfig"]
            assert "responseJsonSchema" not in config
            assert "responseSchema" in config
            assert "additional_properties" not in serialized
            assert "additionalProperties" not in json.dumps(config)
            assert "plan" not in config["responseSchema"]["properties"]
            assert "nullable" not in json.dumps(config["responseSchema"])
            assert "maximum" not in json.dumps(config["responseSchema"])
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
        if field_aggregate is not None:
            with pytest.raises((ProviderError, ModelResponseError)):
                QueryPlanner(gateway, "2026-10-01", context).generate("Số dòng đã đóng?")
            assert len(calls) == 1
            return
        plan = QueryPlanner(gateway, "2026-10-01", context).generate("Tổng học phí đã đóng?")
        if field_aggregate is None:
            assert "SUM(" in compiler.compile(plan).validated.statement.upper()
        else:
            with pytest.raises(SqlValidationError, match="Invalid nested aggregate"):
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
