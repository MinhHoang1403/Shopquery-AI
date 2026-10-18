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

    def route(
        self,
        question: str,
        allowed_routes: frozenset[RouteLabel] | None = None,
    ) -> RouteDecision:
        routes = allowed_routes or frozenset(RouteLabel)
        route_names = ", ".join(sorted(route.value for route in routes))
        prompt = f"""
Classify the ShopQuery question into exactly one route:
- SQL: needs only commerce tables (products, categories, orders, sales, revenue).
- RAG: needs only store policy or shopping-guide documents.
- HYBRID: needs both computed commerce rows and document policy evidence.
- UNSUPPORTED: outside this demo store's data and documents.

Store documents cover shipping eligibility by category code, returns, warranty periods,
product guides and shopping FAQs. A question asking which category codes have free shipping
is a policy lookup (RAG), not an out-of-scope question. Use HYBRID only when an actual table
calculation or product lookup must be combined with one of these document conditions.

Available routes for the selected data source: {route_names}.
These capabilities have already been checked by the application. Downstream pipelines will
query the tables and retrieve the documents. Do not choose UNSUPPORTED merely because the
actual table rows or policy text are not included in this classification prompt.
Return UNSUPPORTED when the required evidence type is unavailable. Never select an unavailable
route. For uploaded workspaces, "commerce tables" means their uploaded tables and "documents"
means only documents uploaded to that same workspace.

Do not answer the question and do not generate SQL.
Examples:
- Top 5 sản phẩm bán chạy nhất? -> SQL
- Chính sách đổi trả là gì? -> RAG
- Top 5 sản phẩm bán chạy có được miễn phí vận chuyển không? -> HYBRID
- Thời tiết Hà Nội hôm nay? -> UNSUPPORTED

Question: {question}
""".strip()
        return self._gateway.generate_structured(prompt, RouteDecision)
