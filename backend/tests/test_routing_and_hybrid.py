"""Offline router, RAG citation, and Hybrid evidence tests."""

from typing import Any

import pytest

from app.rag.pipeline import RagAnswerDraft, RagPipeline
from app.rag.repository import RetrievedChunk
from app.routing.hybrid import HybridAnswerDraft, HybridPipeline
from app.routing.router import QueryRouter, RouteLabel
from app.semantic.wire import TaskProposal
from app.text_to_sql.pipeline import SqlResult
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.query_plan import PlanDecision, PlanField, QueryPlan
from app.text_to_sql.schema_context import default_sql_context
from tests.hybrid_fixtures import explanation_draft
from tests.semantic_fixtures import proposal_for_evidence


class FakeGateway:
    def __init__(self, route: RouteLabel = RouteLabel.HYBRID) -> None:
        self.route = route

    def generate_structured(self, prompt: str, response_model: type[Any]) -> Any:
        if response_model is TaskProposal:
            return proposal_for_evidence(
                {
                    "SQL": "tables",
                    "RAG": "documents",
                    "HYBRID": "both",
                    "UNSUPPORTED": "unavailable",
                }[self.route]
            )
        if response_model is RagAnswerDraft:
            return RagAnswerDraft(answer="Câu trả lời có nguồn.", used_chunk_ids=[11])
        if response_model is HybridAnswerDraft:
            return explanation_draft(prompt, [11])
        raise AssertionError(f"Unexpected response model: {response_model}")

    def generate_text(self, prompt: str) -> str:
        return "grounded"

    def embed_query(self, content: str) -> list[float]:
        return [0.1] * 768


class FakeRepository:
    def retrieve(self, query_vector: list[float], top_k: int = 3) -> list[RetrievedChunk]:
        assert len(query_vector) == 768
        return [
            RetrievedChunk(
                chunk_id=11,
                source_file="shipping_policy.md",
                section_title="Miễn phí vận chuyển",
                content="PHONE và LAPTOP được miễn phí vận chuyển tiêu chuẩn.",
                cosine_distance=0.05,
            )
        ]


class FakeSqlPipeline:
    def run(self, question: str, **kwargs) -> SqlResult:
        return SqlResult(
            answer="SQL rows",
            sql="SELECT 'PHONE' AS category_code",
            rows=[
                {
                    "product_id": 1,
                    "product_name": "Điện thoại SQ 001",
                    "category_code": "PHONE",
                    "total_quantity": 25,
                }
            ],
        )


class SqlPromptGateway:
    def __init__(self) -> None:
        self.prompt = ""

    def generate_structured(self, prompt: str, response_model: type[Any]) -> Any:
        assert response_model is PlanDecision
        self.prompt = prompt
        return PlanDecision(
            plan=QueryPlan(source="t0", fields=[PlanField(alias="n", aggregate="row_count")])
        )

    def generate_text(self, prompt: str) -> str:
        raise AssertionError("Text generation is not expected")


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Top 5 sản phẩm?", RouteLabel.SQL),
        ("Chính sách đổi trả?", RouteLabel.RAG),
        ("Top sản phẩm có miễn phí giao hàng?", RouteLabel.HYBRID),
        ("Thời tiết hôm nay?", RouteLabel.UNSUPPORTED),
    ],
)
def test_router_preserves_structured_label(question: str, expected: RouteLabel) -> None:
    decision = QueryRouter(FakeGateway(expected)).route(question)
    assert decision.route == expected


def test_sql_prompt_requires_category_evidence_for_policy_comparison() -> None:
    gateway = SqlPromptGateway()

    QueryPlanner(gateway, "2026-10-01", default_sql_context()).generate(
        "Top products thuộc danh mục được miễn phí vận chuyển?"
    )

    assert "include category_code and category_name" in gateway.prompt
    assert "infer a category from product_name" in gateway.prompt
    assert "filters only if requested" in gateway.prompt
    assert "Row count has zero arguments" in gateway.prompt
    assert "Do not confuse COUNT rows with non-NULL value counts" in gateway.prompt
    assert "aliases as semantic proof" in gateway.prompt


def test_sql_prompt_requires_explicit_vietnamese_calendar_boundaries() -> None:
    gateway = SqlPromptGateway()

    QueryPlanner(gateway, "2026-10-01", default_sql_context()).generate(
        "Top sản phẩm tháng 9/2025?"
    )

    assert "Asia/Ho_Chi_Minh" in gateway.prompt
    assert "TIMESTAMPTZ values require explicit offsets" in gateway.prompt
    assert "local boundaries +07:00" in gateway.prompt
    assert "values must have no offset" in gateway.prompt
    assert ">= start AND < end" in gateway.prompt


@pytest.mark.parametrize(
    "question",
    [
        "Sản phẩm bán chạy nào được miễn phí vận chuyển?",
        "Top 5 sản phẩm có thời hạn bảo hành bao lâu?",
        "Danh mục doanh thu cao nhất áp dụng đổi trả thế nào?",
        "Laptop bán chạy có chính sách vận chuyển gì?",
        "Sản phẩm AUDIO bán nhiều nhất được bảo hành mấy tháng?",
    ],
)
def test_hybrid_uses_sql_rows_and_policy_citation(question: str) -> None:
    gateway = FakeGateway()
    rag = RagPipeline(gateway, gateway, FakeRepository())
    result = HybridPipeline(FakeSqlPipeline(), rag, gateway).run(question)

    assert result.rows[0]["category_code"] == "PHONE"
    assert result.sources[0].source_file == "shipping_policy.md"
    assert result.sources[0].chunk_id == 11
    assert "PHONE" in result.answer


@pytest.mark.parametrize(
    "question",
    [
        "Danh mục nào miễn phí vận chuyển?",
        "Tôi có bao lâu để đổi trả?",
        "PHONE được bảo hành bao lâu?",
        "Sản phẩm lỗi khi nhận xử lý thế nào?",
        "ShopQuery tính bán chạy ra sao?",
    ],
)
def test_rag_keeps_retrieved_source(question: str) -> None:
    gateway = FakeGateway(RouteLabel.RAG)
    result = RagPipeline(gateway, gateway, FakeRepository()).run(question)
    assert result.sources[0].source_file == "shipping_policy.md"
    assert result.sources[0].section_title == "Miễn phí vận chuyển"
