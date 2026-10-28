"""Top-level chat dispatch with one stable response shape."""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.diagnostics import record_facts
from app.core.errors import ErrorContext, SqlUnsupportedError
from app.rag.pipeline import RagPipeline, Source
from app.routing.hybrid import HybridPipeline
from app.routing.hybrid_evidence import VerificationStatus
from app.routing.router import QueryRouter, RouteDecision, RouteLabel
from app.text_to_sql.answer import ResultColumn
from app.text_to_sql.pipeline import TextToSqlPipeline

INSUFFICIENT_INFORMATION = (
    "Dữ liệu hiện tại chưa có thông tin cần thiết để trả lời chính xác câu hỏi này."
)
logger = logging.getLogger(__name__)


def _unsupported_answer(decision: RouteDecision) -> str:
    if decision.evidence_requirement == "unclear":
        return (
            "Tôi chưa xác định được phạm vi câu hỏi. "
            "Bạn muốn tra quy định hay tính số liệu, cho nhóm và khoảng thời gian nào?"
        )
    return INSUFFICIENT_INFORMATION


@dataclass
class ChatResult:
    answer: str
    route: RouteLabel | None
    sql: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    requested_model: str | None = None
    used_model: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    fallback_error_context: ErrorContext | None = None
    verification_status: VerificationStatus | None = None
    result_columns: tuple[ResultColumn, ...] = ()
    answer_row_indices: tuple[int, ...] | None = None


def _sql_refusal(exc: SqlUnsupportedError) -> ChatResult:
    record_facts(route="UNSUPPORTED")
    if exc.code == "join_aggregate" and exc.aggregate_reason is not None:
        logger.info("SQL request refused: %s (%s)", exc.code, exc.aggregate_reason)
    else:
        logger.info("SQL request refused: %s", exc.code or "unspecified")
    messages = {
        "relationship": (
            "Mình chưa tìm thấy liên kết phù hợp giữa các bảng. "
            "Bạn có thể thiết lập trong Quản lý dữ liệu → Liên kết bảng."
        ),
        "calculation": (
            "Chưa thể xử lý phép tính này chính xác. Bạn có thể xem dữ liệu liên quan."
        ),
    }
    return ChatResult(
        messages.get(
            exc.reason, "Chưa thể xử lý câu hỏi này chính xác trong phạm vi hỗ trợ hiện tại."
        ),
        RouteLabel.UNSUPPORTED,
    )


class ChatService:
    def __init__(
        self,
        router: QueryRouter,
        sql_pipeline: TextToSqlPipeline,
        rag_pipeline: RagPipeline,
        hybrid_pipeline: HybridPipeline,
    ) -> None:
        self._router = router
        self._sql_pipeline = sql_pipeline
        self._rag_pipeline = rag_pipeline
        self._hybrid_pipeline = hybrid_pipeline

    def chat(self, question: str, *, current_question: str | None = None) -> ChatResult:
        decision = self._router.route(
            question,
            **({"current_question": current_question} if current_question is not None else {}),
        )
        route = decision.route
        if route == RouteLabel.SQL:
            result = self._sql_pipeline.run(question)
            return ChatResult(
                result.answer, route, result.sql, result.rows, result_columns=result.result_columns
            )
        if route == RouteLabel.RAG:
            result = self._rag_pipeline.run(question)
            return ChatResult(result.answer, route, sources=result.sources)
        if route == RouteLabel.HYBRID:
            result = self._hybrid_pipeline.run(
                question,
                **(
                    {"classification": decision.policy_intent}
                    if decision.policy_scope == "all_entities" and decision.policy_intent != "none"
                    else {}
                ),
                **({"current_question": current_question} if current_question is not None else {}),
            )
            return ChatResult(
                result.answer,
                route,
                result.sql,
                result.rows,
                result.sources,
                verification_status=result.verification_status,
                result_columns=result.result_columns,
                answer_row_indices=result.answer_row_indices,
            )
        return ChatResult(
            answer=_unsupported_answer(decision),
            route=RouteLabel.UNSUPPORTED,
        )


class DatasetChatService:
    """Dispatch within the capabilities of one selected dataset workspace."""

    def __init__(
        self,
        router: QueryRouter | None,
        sql_pipeline: TextToSqlPipeline | None,
        rag_pipeline: RagPipeline | None,
        hybrid_pipeline: HybridPipeline | None,
        requested_model: str | None = None,
    ) -> None:
        self._router = router
        self._sql_pipeline = sql_pipeline
        self._rag_pipeline = rag_pipeline
        self._hybrid_pipeline = hybrid_pipeline
        self._requested_model = requested_model

    def chat(self, question: str, *, current_question: str | None = None) -> ChatResult:
        allowed = {RouteLabel.UNSUPPORTED}
        if self._sql_pipeline is not None:
            allowed.add(RouteLabel.SQL)
        if self._rag_pipeline is not None:
            allowed.add(RouteLabel.RAG)
        if self._hybrid_pipeline is not None:
            allowed.add(RouteLabel.HYBRID)
        if len(allowed) == 1 or self._router is None:
            return ChatResult(
                "Chưa có đủ dữ liệu để trả lời câu hỏi này. "
                "Bạn hãy kiểm tra các tệp đã tải lên nhé.",
                RouteLabel.UNSUPPORTED,
                requested_model=self._requested_model,
            )
        decision = self._router.route(
            question,
            frozenset(allowed),
            **({"current_question": current_question} if current_question is not None else {}),
        )
        route = decision.route
        if route == RouteLabel.SQL and self._sql_pipeline is not None:
            try:
                result = self._sql_pipeline.run(question)
            except SqlUnsupportedError as exc:
                return _sql_refusal(exc)
            return ChatResult(
                result.answer, route, result.sql, result.rows, result_columns=result.result_columns
            )
        if route == RouteLabel.RAG and self._rag_pipeline is not None:
            result = self._rag_pipeline.run(question)
            return ChatResult(result.answer, route, sources=result.sources)
        if route == RouteLabel.HYBRID and self._hybrid_pipeline is not None:
            try:
                result = self._hybrid_pipeline.run(
                    question,
                    **(
                        {"classification": decision.policy_intent}
                        if decision.policy_scope == "all_entities"
                        and decision.policy_intent != "none"
                        else {}
                    ),
                    **(
                        {"current_question": current_question}
                        if current_question is not None
                        else {}
                    ),
                )
            except SqlUnsupportedError as exc:
                return _sql_refusal(exc)
            return ChatResult(
                result.answer,
                route,
                result.sql,
                result.rows,
                result.sources,
                verification_status=result.verification_status,
                result_columns=result.result_columns,
                answer_row_indices=result.answer_row_indices,
            )
        return ChatResult(
            _unsupported_answer(decision),
            RouteLabel.UNSUPPORTED,
        )
