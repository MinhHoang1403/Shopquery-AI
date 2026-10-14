"""Structured query classification without execution responsibilities."""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.ai.gemini import GenerationGateway


class RouteLabel(StrEnum):
    SQL = "SQL"
    RAG = "RAG"
    HYBRID = "HYBRID"
    UNSUPPORTED = "UNSUPPORTED"


class RouteDecision(BaseModel):
    route: RouteLabel
    reason: str = Field(description="Short reason based on the route definitions")


class QueryRouter:
    def __init__(self, gateway: GenerationGateway) -> None:
        self._gateway = gateway

    def route(self, question: str) -> RouteDecision:
        prompt = f"""
Classify the ShopQuery question into exactly one route:
- SQL: needs only commerce tables (products, categories, orders, sales, revenue).
- RAG: needs only store policy or shopping-guide documents.
- HYBRID: needs both computed commerce rows and document policy evidence.
- UNSUPPORTED: outside this demo store's data and documents.

Do not answer the question and do not generate SQL.
Examples:
- Top 5 sản phẩm bán chạy nhất? -> SQL
- Chính sách đổi trả là gì? -> RAG
- Top 5 sản phẩm bán chạy có được miễn phí vận chuyển không? -> HYBRID
- Thời tiết Hà Nội hôm nay? -> UNSUPPORTED

Question: {question}
""".strip()
        return self._gateway.generate_structured(prompt, RouteDecision)
