"""The same success/refusal contract crosses both real adapters via mock transports."""

import json

import pytest

from app.text_to_sql.query_plan import PlanDecision, PlanField, QueryPlan
from tests.test_plan_providers import gateway_harness, response


@pytest.mark.parametrize("provider", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("supported", [True, False])
def test_sql_draft_schema_survives_both_adapter_serializers(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    supported: bool,
) -> None:
    expected = PlanDecision(
        plan=QueryPlan(source="t0", fields=[PlanField(reference="t0.c0", alias="id")])
        if supported
        else None,
        unsupported_reason=None if supported else "Synthetic unsupported grain",
    )
    content = expected.model_dump_json()
    adapter = "knowledge" if provider == "inetcloud-knowledge" else provider
    gateway, calls = gateway_harness(monkeypatch, adapter, [response(adapter, content)])
    try:
        actual = gateway.generate_structured("Synthetic plan contract only", PlanDecision)
    finally:
        gateway.close()
    assert actual == expected
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    serialized = json.dumps(payload)
    assert "outcome" in serialized and "GenerationDecision" in serialized
    assert "sql" not in PlanDecision.model_fields
