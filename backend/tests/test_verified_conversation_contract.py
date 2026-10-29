"""Trusted verification metadata survives dispatch, API serialization and persistence."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from app.ai.chat import ModelChatService
from app.api.models import ChatRequest, ChatResponse
from app.api.routes import _conversation_detail, _persist_chat_turn
from app.conversations.context import contextual_question
from app.conversations.repository import MessageRecord
from app.core.config import Settings
from app.routing.hybrid import HybridPipeline
from app.routing.router import RouteDecision, RouteLabel
from app.routing.service import DatasetChatService
from tests.semantic_fixtures import proposal_for_evidence
from tests.test_conversation_context import snapshot
from tests.test_evidence_coverage import QUESTION, fixture, pipeline


def test_backend_status_reaches_persistence_and_reload_and_followup_rechecks_evidence(monkeypatch):
    chunk, context, _ = fixture()
    conversation = replace(snapshot(), messages=(), model_id="gemini")
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
    sql, executor, gateway = pipeline(context, rows)
    executor.execute.side_effect = [
        [{"entity_count": 2}],
        [{"entity_id": "U1"}, {"entity_id": "U2"}],
        rows,
    ] * 2
    retrieval = Mock(retrieve=Mock(return_value=[chunk]))
    hybrid = HybridPipeline(sql, retrieval, gateway, context)
    router = Mock()

    def route(question, *_args, current_question=None):
        current = current_question or question
        selection = "not_qualified" if current == "Which units do not qualify?" else "all"
        return RouteDecision(
            task=proposal_for_evidence("both", selection).task(current),
            route=RouteLabel.HYBRID,
            reason="fixture",
            evidence_requirement="both",
            policy_intent=selection,
            policy_scope="all_entities",
        )

    router.route.side_effect = route
    service = ModelChatService(
        Settings(_env_file=None, ai_default_model="gemini"),
        lambda _: DatasetChatService(router, sql, retrieval, hybrid),
    )
    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: gateway)
    stored = []
    repository = Mock()
    repository.add_user_message.side_effect = lambda _, content: MessageRecord(
        len(stored) * 2 + 1,
        "user",
        content,
        None,
        datetime.now(UTC),
    )

    def persist(_, *, content, response_metadata, is_error):
        assert not is_error
        record = MessageRecord(
            len(stored) * 2 + 2, "assistant", content, response_metadata, datetime.now(UTC)
        )
        stored.append(record)
        return record

    repository.add_response_message.side_effect = persist
    repository.get.return_value = conversation
    monkeypatch.setattr("app.api.routes.build_dataset_repository", lambda _: Mock())
    monkeypatch.setattr("app.api.routes.build_workspace_context", lambda *_: context)
    monkeypatch.setattr("app.api.routes.build_dataset_chat_service", lambda *_: service)
    first = _persist_chat_turn(
        repository, conversation, ChatRequest(message=QUESTION), conversation.owner_user_id
    )
    assert first.assistant_message.response.verification_status == "verified_classification"
    assert any(
        c.key == "metric_value" and c.numeric
        for c in first.assistant_message.response.result_columns
    )
    response = ChatResponse.model_validate(stored[0].response_metadata)
    assert response.verification_status == "verified_classification"
    previous_user = MessageRecord(1, "user", QUESTION, None, datetime.now(UTC))
    conversation = replace(conversation, messages=(previous_user, stored[0]))
    reloaded = _conversation_detail(conversation)
    assert reloaded.messages[1].response.verification_status == "verified_classification"
    followup = "Which units do not qualify?"
    assert QUESTION in contextual_question(followup, conversation, conversation.owner_user_id, 13)
    _persist_chat_turn(
        repository, conversation, ChatRequest(message=followup), conversation.owner_user_id
    )
    assert retrieval.retrieve.call_count == 2 and executor.execute.call_count == 6
    assert stored[1].response_metadata["verification_status"] == "verified_classification"
    assert stored[1].response_metadata["answer_row_indices"] == [1]
    assert stored[1].response_metadata["rows"] == rows
    assert "| U1 |" not in stored[1].content and "| U2 |" in stored[1].content
    assert "Previous user questions" in router.route.call_args.args[0]
    assert stored[0].content not in router.route.call_args.args[0]
    assert stored[0].response_metadata["result_envelope"]["premise_trust"] == "reference_only"
    gateway.generate_structured.assert_not_called()


@pytest.mark.parametrize("status", [None, "unverified", "explanation", "refused"])
def test_legacy_or_unverified_hybrid_never_reuses_an_older_verified_turn(status):
    conversation = snapshot()
    now = datetime.now(UTC)
    metadata = {
        "route": "HYBRID",
        "answer": "Successful HTTP, no verified business conclusion",
        "error": None,
        "sql": "SELECT 1",
    }
    if status is not None:
        metadata["verification_status"] = status
    conversation = replace(
        conversation,
        messages=conversation.messages
        + (
            MessageRecord(3, "user", "Use a different policy", None, now),
            MessageRecord(4, "assistant", metadata["answer"], metadata, now),
        ),
    )
    assert (
        contextual_question("Còn lại?", conversation, conversation.owner_user_id, 13) == "Còn lại?"
    )
    assert _conversation_detail(conversation).messages[-1].content == metadata["answer"]


def test_client_cannot_claim_backend_verification():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChatRequest(message=QUESTION, verification_status="verified_classification")
