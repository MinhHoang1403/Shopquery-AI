"""Typed completed evidence is scoped; historical assistant prose never becomes authority."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.models import ChatResponse
from app.api.routes import _chat_response
from app.conversations.context import contextual_question
from app.conversations.repository import MessageRecord
from app.routing.hybrid import HybridPipeline
from app.routing.router import QueryRouter
from app.routing.service import DatasetChatService
from app.semantic.reference import TaskReference
from app.semantic.request import RequestIdentity, catalog_revision, semantic_request
from tests.semantic_fixtures import proposal_for_evidence
from tests.test_conversation_context import snapshot
from tests.test_evidence_coverage import fixture, pipeline


def completed_reference():
    conversation = replace(snapshot(), messages=())
    chunk, context, _ = fixture()
    context = replace(
        context,
        dataset_id=conversation.dataset_id,
        owner_user_id=conversation.owner_user_id,
        table_row_counts={"random_d": 2},
    )
    chunk = replace(
        chunk,
        document_scope=replace(
            chunk.document_scope, dataset_id=context.dataset_id, owner_user_id=context.owner_user_id
        ),
    )
    rows = [
        {"entity_id": "U1", "metric_value": "40.00"},
        {"entity_id": "U2", "metric_value": "0.00"},
    ]
    sql, executor, drafting = pipeline(context, rows)
    executor.execute.side_effect = [
        [{"entity_count": 2}],
        [{"entity_id": "U1"}, {"entity_id": "U2"}],
        rows,
    ] * 2
    gateway = Mock(
        generate_structured=Mock(
            side_effect=[
                proposal_for_evidence("both", "all"),
                proposal_for_evidence("both", "not_qualified"),
            ]
        )
    )
    rag = Mock(retrieve=Mock(return_value=[chunk]))
    service = DatasetChatService(
        QueryRouter(gateway, context=context), sql, rag, HybridPipeline(sql, rag, drafting, context)
    )
    question = "Assess all units using the documented policy."
    with semantic_request(
        RequestIdentity(
            conversation.owner_user_id,
            conversation.conversation_id,
            context.dataset_id,
            question,
            "2026-10-29",
        )
    ):
        response = _chat_response(service.chat(question))
    now = datetime.now(UTC)
    conversation = replace(
        conversation,
        messages=(
            MessageRecord(1, "user", question, None, now),
            MessageRecord(2, "assistant", response.answer, response.model_dump(mode="json"), now),
        ),
    )
    return conversation, context, response, service, rag, executor, gateway


def test_verified_reference_survives_roundtrip_and_followup_reads_fresh_evidence():
    conversation, context, response, service, rag, executor, gateway = completed_reference()
    restored = ChatResponse.model_validate_json(response.model_dump_json())
    assert restored.result_envelope.premise_trust == "verified_result"
    assert restored.result_envelope.semantic_status == "coverage_verified"
    followup = "Which units do not qualify?"
    contextual = contextual_question(
        followup,
        conversation,
        conversation.owner_user_id,
        conversation.dataset_id,
        catalog_revision(context),
    )
    assert '"task_reference"' in contextual
    assert response.answer not in contextual
    with semantic_request(
        RequestIdentity(
            conversation.owner_user_id,
            conversation.conversation_id,
            context.dataset_id,
            followup,
            "2026-10-29",
        )
    ):
        result = service.chat(contextual, current_question=followup)
    assert result.verification_status == "verified_classification"
    assert result.answer_row_indices == (1,)
    assert rag.retrieve.call_count == 2 and executor.execute.call_count == 6
    assert gateway.generate_structured.call_count == 2


@pytest.mark.parametrize(
    "mutation", ["owner", "conversation", "dataset", "revision", "question", "shape"]
)
def test_stale_or_forged_reference_does_not_fall_back_to_legacy_trust(mutation):
    conversation, context, response, *_ = completed_reference()
    metadata = response.model_dump(mode="json")
    reference = metadata["semantic_reference"]
    if mutation in {"owner", "conversation"}:
        reference["request"]["owner_user_id" if mutation == "owner" else "conversation_id"] = str(
            uuid4()
        )
    elif mutation == "dataset":
        reference["request"]["dataset_id"] += 1
    elif mutation == "revision":
        reference["request"]["catalog_revision"] = "0" * 64
    elif mutation == "question":
        reference["request"]["question"] = "A different question"
    else:
        metadata["semantic_reference"] = ["not a reference"]
    conversation = replace(
        conversation,
        messages=(
            conversation.messages[0],
            replace(conversation.messages[1], response_metadata=metadata),
        ),
    )
    current = "Which units do not qualify?"
    assert (
        contextual_question(
            current,
            conversation,
            conversation.owner_user_id,
            conversation.dataset_id,
            catalog_revision(context),
        )
        == current
    )


def test_document_answer_claim_cannot_mint_a_verified_task_reference():
    _, _, response, *_ = completed_reference()
    data = response.semantic_reference.model_dump(mode="json")
    data["task"] = {"operation": "explain", "question": data["request"]["question"]}
    with pytest.raises(ValidationError):
        TaskReference.model_validate(data)
