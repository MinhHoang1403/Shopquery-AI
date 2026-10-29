"""RAG citation validation does not prove model claims or semantic entailment."""

import json
from unittest.mock import Mock

import pytest

from app.core.errors import ModelResponseError
from app.rag.pipeline import RagAnswerDraft, RagPipeline, RagResult, Source
from app.rag.repository import RetrievedChunk
from app.routing.router import RouteDecision, RouteLabel
from app.routing.service import ChatService, DatasetChatService
from tests.test_plan_providers import gateway_harness, response


def chunk():
    return RetrievedChunk(11, "synthetic.md", "Policy", "Evidence for the selected workspace.", 0.1)


@pytest.mark.parametrize(
    "claim", ["answered", "partially_answered", "insufficient_evidence", "unsupported"]
)
def test_answerability_is_a_model_claim_not_a_verification(claim):
    gateway = Mock()
    gateway.generate_structured.return_value = RagAnswerDraft(
        answer="Synthetic response", used_chunk_ids=[11], answerability=claim
    )
    result = RagPipeline(None, gateway, None).answer_from_chunks("Question?", [chunk()])
    assert result.answerability_claim == claim
    assert result.grounding_status == "citation_validated"
    assert not hasattr(result, "verified")


def test_missing_claim_is_unverified():
    gateway = Mock()
    gateway.generate_structured.return_value = RagAnswerDraft(answer="Text", used_chunk_ids=[11])
    result = RagPipeline(None, gateway, None).answer_from_chunks("Question?", [chunk()])
    assert result.answerability_claim == "unverified"


@pytest.mark.parametrize("answer", ["", "  ", "\n\t"])
def test_empty_answer_is_rejected_even_with_valid_citation(answer):
    gateway = Mock()
    gateway.generate_structured.return_value = RagAnswerDraft(
        answer=answer, used_chunk_ids=[11], answerability="answered"
    )
    with pytest.raises(ModelResponseError):
        RagPipeline(None, gateway, None).answer_from_chunks("Question?", [chunk()])


def test_citations_cannot_escape_retrieved_chunks():
    gateway = Mock()
    gateway.generate_structured.return_value = RagAnswerDraft(
        answer="Text", used_chunk_ids=[99], answerability="answered"
    )
    with pytest.raises(ModelResponseError):
        RagPipeline(None, gateway, None).answer_from_chunks("Question?", [chunk()])


@pytest.mark.parametrize("service_type", [ChatService, DatasetChatService])
def test_rag_claim_and_citation_validation_survive_api_metadata_roundtrip(service_type):
    from app.api.models import ChatResponse
    from app.api.routes import _chat_response

    router, sql, rag, hybrid = Mock(), Mock(), Mock(), Mock()
    from app.semantic.task import SemanticTask

    router.route.return_value = RouteDecision(
        task=SemanticTask(operation="explain", question="Question?"),
        route=RouteLabel.RAG,
        reason="Documents",
        evidence_requirement="documents",
        policy_intent="none",
        policy_scope="unspecified",
    )
    rag.run.return_value = RagResult(
        "Text",
        [Source(11, "synthetic.md", "Policy", "Evidence")],
        [chunk()],
        answerability_claim="answered",
        grounding_status="citation_validated",
    )
    response_data = _chat_response(service_type(router, sql, rag, hybrid).chat("Question?"))
    restored = ChatResponse.model_validate(response_data.model_dump(mode="json"))
    assert restored.rag_answerability_claim == "answered"
    assert restored.rag_grounding_status == "citation_validated"
    assert restored.verification_status is None


def test_legacy_public_response_is_compatible_and_not_verified():
    from app.api.models import ChatResponse

    restored = ChatResponse.model_validate({"answer": "Legacy", "route": "RAG"})
    assert restored.rag_answerability_claim is None
    assert restored.rag_grounding_status is None
    assert restored.verification_status is None


def test_telemetry_only_exports_fixed_safe_enums():
    from app.core.diagnostics import diagnostic_request, record_facts

    with diagnostic_request() as trace:
        record_facts(
            rag_answerability_claim="answered",
            rag_grounding_status="citation_validated",
            conversation_premise="reference_only",
            user_question="PRIVATE synthetic content",
        )
        assert trace.facts["rag_answerability_claim"] == "answered"
        assert trace.facts["rag_grounding_status"] == "citation_validated"
        assert trace.facts["conversation_premise"] == "reference_only"
        assert "user_question" not in trace.facts
        record_facts(rag_answerability_claim="PRIVATE synthetic content")
        assert trace.facts["rag_answerability_claim"] == "answered"


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_provider_wire_includes_typed_claim_and_uses_one_attempt(monkeypatch, provider):
    payload = json.dumps(
        {"answer": "Synthetic", "used_chunk_ids": [11], "answerability": "answered"}
    )
    gateway, calls = gateway_harness(monkeypatch, provider, [response(provider, payload)])
    try:
        result = gateway.generate_structured("Synthetic question", RagAnswerDraft)
        assert result.answerability == "answered"
        body = json.loads(calls[0].content)
        schema = (
            body["response_format"]["json_schema"]["schema"]
            if provider == "knowledge"
            else body["generationConfig"]["responseSchema"]
        )
        assert set(schema["properties"]["answerability"]["enum"]) == {
            "answered",
            "partially_answered",
            "insufficient_evidence",
            "unsupported",
            "unverified",
        }
        assert len(calls) == 1
    finally:
        gateway.close()
