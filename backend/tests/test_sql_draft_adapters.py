"""The same success/refusal contract crosses both real adapters via mock transports."""

import json

import httpx
import pytest

from app.text_to_sql.generator import SqlDraft
from tests.test_gemini import _build_harness
from tests.test_providers import completion, harness


@pytest.mark.parametrize("provider", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("supported", [True, False])
def test_sql_draft_schema_survives_both_adapter_serializers(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    supported: bool,
) -> None:
    expected = SqlDraft(
        sql="SELECT id FROM uploaded_data.synthetic" if supported else "",
        unsupported_reason=None if supported else "Synthetic unsupported grain",
    )
    content = expected.model_dump_json()
    if provider == "gemini":
        response = httpx.Response(
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
        controlled = _build_harness(monkeypatch, [response])
        gateway, calls = controlled.gateway, controlled.calls
    else:
        gateway, calls = harness(monkeypatch, [completion(content)])
    try:
        actual = gateway.generate_structured("Synthetic SQL contract only", SqlDraft)
    finally:
        gateway.close()
    assert actual == expected
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    serialized = json.dumps(payload)
    assert "unsupported_reason" in serialized
    assert "empty string when unsupported" in serialized
    assert "null on success" in serialized
