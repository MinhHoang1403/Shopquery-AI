import json

import pytest
from pydantic import ValidationError

from app.core.errors import ContractConversionError, ModelResponseError
from app.text_to_sql.generation_contract import GenerationDecision
from app.text_to_sql.query_plan import PlanDecision
from tests.test_gemini import _build_harness
from tests.test_plan_providers import response


def wire_plan():
    return {
        "outcome": "query",
        "reason": "",
        "source": "t0",
        "fields": [{"reference": "e0", "alias": "fact_row_count"}],
        "expressions": [
            {"operation": "row_count", "arguments": [], "value": "", "value_type": "none"}
        ],
        "filters": [],
        "group_by": [],
        "sort": [],
        "limit": 0,
        "relationships": [],
        "where": "",
        "having": "",
    }


def test_native_sdk_wire_is_flat_without_nullable_unions_refs_or_bounds(monkeypatch):
    payload = wire_plan()
    harness = _build_harness(monkeypatch, [response("gemini", json.dumps(payload))])
    try:
        actual = harness.gateway.generate_structured("Synthetic only", PlanDecision)
    finally:
        harness.close()
    assert actual.plan.limit is None
    assert actual.plan.expressions[0].operation == "row_count"
    assert len(harness.calls) == 1
    config = json.loads(harness.calls[0].content)["generationConfig"]
    encoded = json.dumps(config["responseSchema"])
    for forbidden in (
        "anyOf",
        "$ref",
        "$defs",
        "nullable",
        "additionalProperties",
        "maxItems",
        "maxLength",
    ):
        assert forbidden not in encoded
    assert "responseJsonSchema" not in config
    assert set(config["responseSchema"]["required"]) == set(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"limit": 1001},
        {"limit": -1},
        {"sql": "DROP TABLE users"},
        {"fields": [{"reference": "e0", "alias": "x", "aggregate": "sum"}]},
        {
            "expressions": [
                {"operation": "row_count", "arguments": [], "value": "9", "value_type": "none"}
            ]
        },
        {
            "expressions": [
                {"operation": "sum", "arguments": ["e0"], "value": "", "value_type": "none"}
            ]
        },
    ],
)
def test_compact_contract_does_not_remove_backend_validation(changes):
    with pytest.raises((ValidationError, ContractConversionError)):
        GenerationDecision.model_validate({**wire_plan(), **changes}).decision()


def test_invalid_wire_is_one_request_not_a_schema_repair_loop(monkeypatch):
    harness = _build_harness(
        monkeypatch, [response("gemini", json.dumps({**wire_plan(), "limit": 1001}))]
    )
    try:
        with pytest.raises(ModelResponseError):
            harness.gateway.generate_structured("Synthetic only", PlanDecision)
    finally:
        harness.close()
    assert len(harness.calls) == 1
