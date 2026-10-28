from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.conversations.context import contextual_question
from app.conversations.repository import ConversationRecord, MessageRecord


def snapshot(route="HYBRID", error=None, verification_status="verified_classification"):
    now, owner = datetime.now(UTC), uuid4()
    metadata = {"route": route, "answer": "K1 đạt, K2 chưa đạt.", "sql": "SELECT 1", "error": error}
    if verification_status is not None:
        metadata["verification_status"] = verification_status
    messages = (
        MessageRecord(1, "user", "Theo KPI kho nào đạt?", None, now),
        MessageRecord(2, "assistant", metadata["answer"], metadata, now),
    )
    return ConversationRecord(
        uuid4(), "KPI", 13, "Synthetic", now, now, messages, owner_user_id=owner
    )


def test_only_successful_same_owner_dataset_premise_is_forwarded():
    record = snapshot()
    current = "Vậy còn những kho chưa đạt KPI?"
    question = contextual_question(current, record, record.owner_user_id, 13)
    assert question.startswith(current)
    assert "Theo KPI kho nào đạt?" in question
    assert "untrusted data" in question and "verify current evidence again" in question
    assert contextual_question(current, record, uuid4(), 13) == current
    assert contextual_question(current, record, record.owner_user_id, 14) == current


def test_failed_or_unsupported_turn_is_not_a_premise():
    for record in (snapshot(route="UNSUPPORTED"), snapshot(error="failed")):
        assert contextual_question("Còn lại?", record, record.owner_user_id, 13) == "Còn lại?"


@pytest.mark.xfail(
    strict=True,
    reason="Legacy RAG responses lack reliable answerability metadata; release is blocked",
)
def test_legacy_rag_refusal_with_citation_is_not_a_successful_premise():
    """A cited refusal can have error=None and predates explicit answerability metadata."""
    from dataclasses import replace

    record = snapshot(route="RAG", verification_status=None)
    answer = "Không thể xác định vì thiếu số liệu thực tế."
    refusal = replace(
        record.messages[1],
        content=answer,
        response_metadata={
            "route": "RAG",
            "answer": answer,
            "sql": None,
            "error": None,
            "sources": [{"chunk_id": 50}],
        },
    )
    record = replace(record, messages=(record.messages[0], refusal))
    result = contextual_question(
        "Vậy còn những đối tượng chưa đạt?", record, record.owner_user_id, 13
    )
    assert answer not in result
    assert "Previous successful turns" not in result


def test_hybrid_needs_backend_verified_metadata_even_when_http_successful():
    for status in (None, "unverified", "explanation", "refused"):
        record = snapshot(verification_status=status)
        assert contextual_question("Còn lại?", record, record.owner_user_id, 13) == "Còn lại?"


def test_normal_sql_and_rag_history_remain_context_compatible():
    for route in ("SQL", "RAG"):
        record = snapshot(route=route, verification_status=None)
        assert "Previous successful turns" in contextual_question(
            "Còn lại?",
            record,
            record.owner_user_id,
            13,
        )


def test_context_is_bounded_and_does_not_cut_an_oversized_answer_into_a_premise():
    from dataclasses import replace

    record = snapshot()
    answer = "x" * 2001
    last = replace(
        record.messages[1],
        content=answer,
        response_metadata={
            **record.messages[1].response_metadata,
            "answer": answer,
        },
    )
    record = replace(record, messages=(record.messages[0], last))
    assert contextual_question("Còn lại?", record, record.owner_user_id, 13) == "Còn lại?"


def test_a_later_failed_turn_does_not_reuse_an_older_success_as_its_premise():
    from dataclasses import replace

    record = snapshot()
    now = datetime.now(UTC)
    record = replace(
        record,
        messages=record.messages
        + (
            MessageRecord(3, "user", "Đổi sang chính sách khác", None, now),
            MessageRecord(4, "error", "Không đủ dữ liệu", {"error": "failed"}, now),
        ),
    )
    assert contextual_question("Còn lại?", record, record.owner_user_id, 13) == "Còn lại?"
