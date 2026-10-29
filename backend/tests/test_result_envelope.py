"""Uniform server result states do not promote citations or legacy text to proof."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.api.models import ChatResponse
from app.conversations.context import contextual_question
from tests.test_conversation_context import snapshot


@pytest.mark.parametrize(
    "route,fields,evidence,trust",
    [
        ("SQL", {"sql": "SELECT 1"}, "sql_executed", "reference_only"),
        (
            "RAG",
            {
                "sources": [
                    {
                        "chunk_id": 1,
                        "source_file": "s.md",
                        "section_title": "S",
                        "content": "Evidence",
                    }
                ],
                "rag_answerability_claim": "answered",
                "rag_grounding_status": "citation_validated",
            },
            "citation_validated",
            "reference_only",
        ),
        (
            "RAG",
            {
                "sources": [
                    {
                        "chunk_id": 1,
                        "source_file": "s.md",
                        "section_title": "S",
                        "content": "Evidence",
                    }
                ],
                "rag_answerability_claim": "insufficient_evidence",
                "rag_grounding_status": "citation_validated",
            },
            "citation_validated",
            "ineligible",
        ),
        ("HYBRID", {"sql": "SELECT 1", "verification_status": "unverified"}, "none", "ineligible"),
    ],
)
def test_route_states_survive_response_roundtrip(route, fields, evidence, trust):
    response = ChatResponse(answer="Synthetic", route=route, **fields)
    envelope = ChatResponse.model_validate_json(response.model_dump_json()).result_envelope
    assert envelope.evidence == evidence and envelope.premise_trust == trust
    assert envelope.semantic_status == "unverified"


def test_forged_or_inconsistent_envelope_cannot_reach_history():
    response = ChatResponse(answer="Text", route="SQL", sql="SELECT 1").model_dump()
    response["result_envelope"]["premise_trust"] = "verified_result"
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(response)
    response["result_envelope"]["premise_trust"] = "ineligible"
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(response)


def test_bad_persisted_envelope_cannot_fall_back_to_legacy_trust():
    record = snapshot()
    last = record.messages[1]
    metadata = {**last.response_metadata, "result_envelope": {"premise_trust": "verified_result"}}
    record = replace(
        record, messages=(record.messages[0], replace(last, response_metadata=metadata))
    )
    assert contextual_question("Còn lại?", record, record.owner_user_id, 13) == "Còn lại?"


def test_legacy_rag_history_remains_readable_but_ineligible():
    response = ChatResponse.model_validate({"answer": "Legacy", "route": "RAG"})
    assert response.answer == "Legacy"
    assert response.result_envelope.premise_trust == "ineligible"
