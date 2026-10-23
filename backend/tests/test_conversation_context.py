from datetime import UTC, datetime
from uuid import uuid4

from app.conversations.context import contextual_question
from app.conversations.repository import ConversationRecord, MessageRecord


def snapshot(route="HYBRID", error=None):
    now, owner = datetime.now(UTC), uuid4()
    metadata = {"route": route, "answer": "K1 đạt, K2 chưa đạt.", "sql": "SELECT 1", "error": error}
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
