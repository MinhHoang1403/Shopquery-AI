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


def test_sql_history_remains_context_compatible():
    record = snapshot(route="SQL", verification_status=None)
    context = contextual_question("Còn lại?", record, record.owner_user_id, 13)
    assert "Previous user questions" in context
    assert record.messages[0].content in context
    assert record.messages[1].content not in context


def rag_record(claim, *, grounding="citation_validated", sources=None):
    from dataclasses import replace

    record = snapshot(route="RAG", verification_status=None)
    metadata = {
        **record.messages[1].response_metadata,
        "rag_answerability_claim": claim,
        "rag_grounding_status": grounding,
        "sources": [{"chunk_id": 50}] if sources is None else sources,
    }
    return replace(
        record,
        messages=(record.messages[0], replace(record.messages[1], response_metadata=metadata)),
    )


def test_answered_rag_is_question_only_untrusted_reference_not_a_verified_premise():
    record = rag_record("answered")
    question = contextual_question("Còn điều kiện khác?", record, record.owner_user_id, 13)
    assert question.startswith("Còn điều kiện khác?")
    assert record.messages[0].content in question
    assert record.messages[1].content not in question
    assert "Previous successful turns" not in question
    assert "not evidence" in question
    assert contextual_question("Còn lại?", record, uuid4(), 13) == "Còn lại?"
    assert contextual_question("Còn lại?", record, record.owner_user_id, 14) == "Còn lại?"


def test_self_claimed_answered_refusal_is_never_treated_as_a_verified_answer():
    from dataclasses import replace

    record = rag_record("answered")
    answer = "Không có đủ bằng chứng để đưa ra kết luận."
    message = replace(
        record.messages[1],
        content=answer,
        response_metadata={**record.messages[1].response_metadata, "answer": answer},
    )
    record = replace(record, messages=(record.messages[0], message))
    context = contextual_question("Vậy còn các đối tượng khác?", record, record.owner_user_id, 13)
    assert record.messages[0].content in context
    assert answer not in context
    assert "Previous successful turns" not in context
    assert '"kind": "verified"' not in context
    assert '"kind": "reference_only"' in context and "not evidence" in context


@pytest.mark.parametrize(
    "claim", [None, "unverified", "partially_answered", "insufficient_evidence", "unsupported"]
)
def test_insufficient_partial_unsupported_or_legacy_rag_is_not_a_premise(claim):
    record = rag_record(claim)
    assert contextual_question("Còn lại?", record, record.owner_user_id, 13) == "Còn lại?"


def test_claim_answered_without_validated_citations_has_no_reference():
    for record in (
        rag_record("answered", grounding=None),
        rag_record("answered", sources=[]),
    ):
        assert contextual_question("Còn lại?", record, record.owner_user_id, 13) == "Còn lại?"


@pytest.mark.parametrize("rag_first", [True, False])
def test_mixed_context_keeps_chronological_order_and_only_latest_two(rag_first):
    from dataclasses import replace

    rag = rag_record("answered")
    verified = snapshot()
    now = datetime.now(UTC)
    rag_messages = (
        MessageRecord(3 if rag_first else 5, "user", "RAG question", None, now),
        replace(rag.messages[1], message_id=4 if rag_first else 6),
    )
    verified_messages = (
        MessageRecord(5 if rag_first else 3, "user", "Verified question", None, now),
        replace(verified.messages[1], message_id=6 if rag_first else 4),
    )
    older = (
        MessageRecord(1, "user", "Old question", None, now),
        replace(verified.messages[1], message_id=2),
    )
    record = replace(verified, messages=older + rag_messages + verified_messages)
    text = contextual_question("Current question", record, record.owner_user_id, 13)
    assert text.startswith("Current question")
    assert "Old question" not in text
    assert "RAG question" in text and "Verified question" in text
    assert (text.index("RAG question") < text.index("Verified question")) == rag_first
    assert '"kind": "reference_only"' in text


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


@pytest.mark.parametrize("reply_id", [1, 99, True, "1", None])
def test_persisted_response_must_match_its_actual_user_turn(reply_id):
    from dataclasses import replace

    record = snapshot()
    metadata = {**record.messages[1].response_metadata, "turn_user_message_id": reply_id}
    record = replace(
        record,
        messages=(record.messages[0], replace(record.messages[1], response_metadata=metadata)),
    )
    current = "Còn lại?"
    contextual = contextual_question(current, record, record.owner_user_id, record.dataset_id)
    assert (contextual != current) is (type(reply_id) is int and reply_id == 1)


@pytest.mark.parametrize("metadata", [["invalid"], "invalid", 17, True])
def test_non_object_persisted_metadata_cannot_be_used_as_a_premise(metadata):
    from dataclasses import replace

    record = snapshot()
    record = replace(
        record,
        messages=(record.messages[0], replace(record.messages[1], response_metadata=metadata)),
    )
    assert (
        contextual_question("Còn lại?", record, record.owner_user_id, record.dataset_id)
        == "Còn lại?"
    )
