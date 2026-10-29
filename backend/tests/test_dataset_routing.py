"""Capability-aware dispatch for uploaded dataset workspaces."""

from dataclasses import dataclass
from typing import Any

import pytest

from app.routing.router import RouteDecision, RouteLabel
from app.routing.service import DatasetChatService
from tests.semantic_fixtures import proposal_for_evidence


class FakeRouter:
    def __init__(self, route: RouteLabel) -> None:
        self.route_label = route
        self.allowed: frozenset[RouteLabel] | None = None

    def route(self, question: str, allowed_routes: frozenset[RouteLabel]) -> RouteDecision:
        assert question
        self.allowed = allowed_routes
        return RouteDecision(
            task=proposal_for_evidence(
                {
                    "SQL": "tables",
                    "RAG": "documents",
                    "HYBRID": "both",
                    "UNSUPPORTED": "unavailable",
                }[self.route_label]
            ).task(question),
            policy_intent="none",
            policy_scope="unspecified",
            evidence_requirement={
                "SQL": "tables",
                "RAG": "documents",
                "HYBRID": "both",
                "UNSUPPORTED": "unavailable",
            }[self.route_label],
            route=self.route_label,
            reason="fixture",
        )


@dataclass
class PipelineResult:
    answerability_claim: str | None = None
    grounding_status: str | None = None
    result_columns: tuple = ()
    answer_row_indices: tuple | None = None
    answer: str = "grounded"
    sql: str = "SELECT 1"
    rows: list[dict[str, Any]] | None = None
    sources: list[Any] | None = None
    verification_status: str = "unverified"


class FakePipeline:
    def run(self, question: str, **kwargs) -> PipelineResult:
        assert question
        return PipelineResult(rows=[{"value": 1}], sources=[])


@pytest.mark.parametrize(
    ("route", "has_sql", "has_rag", "expected"),
    [
        (RouteLabel.SQL, True, False, {RouteLabel.SQL, RouteLabel.UNSUPPORTED}),
        (RouteLabel.RAG, False, True, {RouteLabel.RAG, RouteLabel.UNSUPPORTED}),
        (
            RouteLabel.HYBRID,
            True,
            True,
            {
                RouteLabel.SQL,
                RouteLabel.RAG,
                RouteLabel.HYBRID,
                RouteLabel.UNSUPPORTED,
            },
        ),
    ],
)
def test_routes_only_through_available_capabilities(
    route: RouteLabel,
    has_sql: bool,
    has_rag: bool,
    expected: set[RouteLabel],
) -> None:
    router = FakeRouter(route)
    sql = FakePipeline() if has_sql else None
    rag = FakePipeline() if has_rag else None
    hybrid = FakePipeline() if has_sql and has_rag else None
    service = DatasetChatService(router, sql, rag, hybrid)  # type: ignore[arg-type]

    result = service.chat("Câu hỏi có bằng chứng?")

    assert router.allowed == frozenset(expected)
    assert result.route == route


def test_empty_workspace_does_not_call_router() -> None:
    router = FakeRouter(RouteLabel.SQL)
    service = DatasetChatService(router, None, None, None)  # type: ignore[arg-type]

    result = service.chat("Có dữ liệu không?")

    assert result.route == RouteLabel.UNSUPPORTED
    assert router.allowed is None


def test_unavailable_route_never_fabricates_a_pipeline_result() -> None:
    router = FakeRouter(RouteLabel.RAG)
    service = DatasetChatService(
        router,
        FakePipeline(),
        None,
        None,  # type: ignore[arg-type]
    )

    result = service.chat("Chính sách là gì?")

    assert result.route == RouteLabel.UNSUPPORTED
    assert result.sql is None
    assert result.rows == []
    assert result.sources == []
