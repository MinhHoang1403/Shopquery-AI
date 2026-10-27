"""One explicit generation outcome converts to the common validated internal plan."""

import json

import pytest
from pydantic import ValidationError

from app.core.errors import ProviderError
from app.text_to_sql.query_plan import PlanDecision
from tests.test_providers import completion, harness


def wire(**updates):
    return {
        "outcome": "query",
        "reason": "",
        "source": "t0",
        "grouping": "entity",
        "fields": [{"reference": "e0", "alias": "rows"}],
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
        **updates,
    }


def test_knowledge_explicit_outcome_uses_existing_generation_contract(monkeypatch):
    gateway, calls = harness(monkeypatch, [completion(json.dumps(wire()))])
    try:
        result = gateway.generate_structured("Count rows", PlanDecision)
        assert result.plan.source == "t0" and result.plan.expressions[0].operation == "row_count"
        payload = json.loads(calls[0].content)
        schema = payload["response_format"]["json_schema"]
        assert schema["name"] == "KnowledgeGenerationDecision" and schema["strict"]
        assert (
            "outcome" in schema["schema"]["required"]
            and "plan" not in schema["schema"]["properties"]
        )
        assert len(calls) == 1
    finally:
        gateway.close()


@pytest.mark.parametrize(
    "payload",
    [
        wire(reason="Simultaneous unsupported"),
        wire(outcome="unsupported", reason="Unavailable"),
        wire(outcome="unsupported", reason="", source="", fields=[], expressions=[]),
    ],
)
def test_explicit_conflicting_or_missing_outcomes_never_repair_or_retry(monkeypatch, payload):
    gateway, calls = harness(monkeypatch, [completion(json.dumps(payload))])
    try:
        with pytest.raises(ProviderError):
            gateway.generate_structured("Q", PlanDecision)
        assert len(calls) == 1
    finally:
        gateway.close()


@pytest.mark.parametrize(
    "payload,branch",
    [
        (
            {
                "plan": {"source": "t0", "fields": [{"reference": "t0.c0", "alias": "x"}]},
                "unsupported_reason": "Both",
            },
            "outcome_conflict",
        ),
        ({"plan": None, "unsupported_reason": ""}, "outcome_missing"),
    ],
)
def test_internal_outcome_validator_has_safe_typed_branch(payload, branch):
    with pytest.raises(ValidationError) as caught:
        PlanDecision.model_validate(payload)
    assert caught.value.errors(include_input=False)[0]["type"] == branch
