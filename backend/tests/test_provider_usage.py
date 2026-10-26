import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.diagnostics import diagnostic_request, record_provider_tokens
from app.core.errors import ModelResponseError
from app.text_to_sql.query_plan import PlanDecision
from tests.test_plan_providers import gateway_harness, response
from tests.test_planning_outcomes import wire


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_actual_adapters_account_for_one_logical_generation_without_content(monkeypatch, provider):
    gateway, calls = gateway_harness(
        monkeypatch, provider, [response(provider, json.dumps(wire()))]
    )
    try:
        with diagnostic_request() as trace:
            gateway.generate_structured("PRIVATE_INPUT", PlanDecision)
        assert trace.facts["generation_calls"] == 1 and len(calls) == 1
        assert "PRIVATE_INPUT" not in str(trace.events)
    finally:
        gateway.close()


def test_token_metadata_is_bounded_numeric_only_and_unknown_is_not_zero():
    with diagnostic_request() as trace:
        record_provider_tokens(None)
        assert "total_tokens" not in trace.facts
        record_provider_tokens(
            {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15, "private": "secret"}
        )
        record_provider_tokens(
            SimpleNamespace(prompt_token_count=8, candidates_token_count=2, total_token_count=10)
        )
        record_provider_tokens({"input_tokens": -1, "output_tokens": True, "total_tokens": 10**30})
    assert (
        trace.facts["input_tokens"] == 20
        and trace.facts["output_tokens"] == 5
        and trace.facts["total_tokens"] == 25
    )
    assert "secret" not in str(trace.events)


def test_nonfinite_embedding_is_refused_before_vector_repository(monkeypatch):
    from app.ai.gemini import GeminiGateway
    from app.core.config import Settings

    gateway = GeminiGateway.__new__(GeminiGateway)
    gateway._settings = Settings(_env_file=None)
    gateway._request = Mock(
        return_value=SimpleNamespace(embeddings=[SimpleNamespace(values=[float("nan")] * 768)])
    )
    with diagnostic_request() as trace, pytest.raises(ModelResponseError):
        gateway.embed_query("Fixture")
    assert trace.facts["query_embedding_calls"] == 1
