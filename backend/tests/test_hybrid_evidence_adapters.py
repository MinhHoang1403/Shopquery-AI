"""The internal Hybrid DTO crosses both adapters without real network access."""

import json

import httpx
import pytest

from app.routing.hybrid_evidence import HybridAnswerDraft
from tests.hybrid_fixtures import classification_draft
from tests.test_gemini import _build_harness
from tests.test_providers import completion, harness


@pytest.mark.parametrize("provider", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("mode", ["classification", "explanation"])
def test_hybrid_evidence_schema_survives_both_adapters(monkeypatch, provider, mode):
    expected = classification_draft([{"entity_id": "S1", "total": "0.00"}], ["not_qualified"], 22)
    if mode == "explanation":
        expected = HybridAnswerDraft(
            mode=mode,
            language="vi",
            identity_fields=[],
            metric_field=None,
            rule_id=None,
            decisions=[],
            notes=[{"chunk_id": 22, "quote": "Synthetic evidence"}],
            used_chunk_ids=[22],
        )
    content = expected.model_dump_json()
    if provider == "gemini":
        controlled = _build_harness(
            monkeypatch,
            [
                httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {
                                "content": {"parts": [{"text": content}], "role": "model"},
                                "finishReason": "STOP",
                            }
                        ],
                    },
                )
            ],
        )
        gateway, calls = controlled.gateway, controlled.calls
    else:
        gateway, calls = harness(monkeypatch, [completion(content)])
    try:
        actual = gateway.generate_structured("Synthetic evidence only", HybridAnswerDraft)
    finally:
        gateway.close()
    assert actual == expected and len(calls) == 1
    payload = json.dumps(json.loads(calls[0].content))
    assert all(
        field in payload
        for field in (
            "entity_values",
            "supporting_chunk_ids",
            "identity_fields",
            "metric_field",
            "rule_id",
        )
    )
