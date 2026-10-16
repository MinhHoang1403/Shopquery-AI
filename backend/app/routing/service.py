"""Top-level chat dispatch with one stable response shape."""

from dataclasses import dataclass, field
from typing import Any

from app.rag.pipeline import RagPipeline, Source
from app.routing.hybrid import HybridPipeline
from app.routing.router import QueryRouter, RouteLabel
from app.text_to_sql.pipeline import TextToSqlPipeline


@dataclass
class ChatResult:
    answer: str
    route: RouteLabel
    sql: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)


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

    def chat(self, question: str) -> ChatResult:
        route = self._router.route(question).route
        if route == RouteLabel.SQL:
            result = self._sql_pipeline.run(question)
            return ChatResult(result.answer, route, result.sql, result.rows)
        if route == RouteLabel.RAG:
            result = self._rag_pipeline.run(question)
            return ChatResult(result.answer, route, sources=result.sources)
        if route == RouteLabel.HYBRID:
            result = self._hybrid_pipeline.run(question)
            return ChatResult(result.answer, route, result.sql, result.rows, result.sources)
        return ChatResult(
            answer=(
                "ShopQuery AI không hỗ trợ yêu cầu này vì nó nằm ngoài dữ liệu bán hàng "
                "và tài liệu cửa hàng hiện có."
            ),
            route=RouteLabel.UNSUPPORTED,
        )


class DatasetChatService:
    """Dispatch within the capabilities of one selected dataset workspace."""

    def __init__(
        self,
        router: QueryRouter,
        sql_pipeline: TextToSqlPipeline | None,
        rag_pipeline: RagPipeline | None,
        hybrid_pipeline: HybridPipeline | None,
    ) -> None:
        self._router = router
        self._sql_pipeline = sql_pipeline
        self._rag_pipeline = rag_pipeline
        self._hybrid_pipeline = hybrid_pipeline

    def chat(self, question: str) -> ChatResult:
        allowed = {RouteLabel.UNSUPPORTED}
        if self._sql_pipeline is not None:
            allowed.add(RouteLabel.SQL)
        if self._rag_pipeline is not None:
            allowed.add(RouteLabel.RAG)
        if self._hybrid_pipeline is not None:
            allowed.add(RouteLabel.HYBRID)
        if len(allowed) == 1:
            return ChatResult(
                "Bộ dữ liệu chưa có bảng hoặc tài liệu để trả lời câu hỏi.",
                RouteLabel.UNSUPPORTED,
            )
        route = self._router.route(question, frozenset(allowed)).route
        if route == RouteLabel.SQL and self._sql_pipeline is not None:
            result = self._sql_pipeline.run(question)
            return ChatResult(result.answer, route, result.sql, result.rows)
        if route == RouteLabel.RAG and self._rag_pipeline is not None:
            result = self._rag_pipeline.run(question)
            return ChatResult(result.answer, route, sources=result.sources)
        if route == RouteLabel.HYBRID and self._hybrid_pipeline is not None:
            result = self._hybrid_pipeline.run(question)
            return ChatResult(result.answer, route, result.sql, result.rows, result.sources)
        return ChatResult(
            "Bộ dữ liệu không có đủ loại nguồn để trả lời câu hỏi này.",
            RouteLabel.UNSUPPORTED,
        )
