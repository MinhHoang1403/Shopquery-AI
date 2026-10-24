from unittest.mock import Mock

import pytest

from app.core.errors import ProviderError
from app.routing.router import QueryRouter, RouteLabel
from app.routing.service import DatasetChatService
from tests.test_dataset_routing import FakePipeline


@pytest.mark.parametrize("route", [RouteLabel.SQL, RouteLabel.RAG, RouteLabel.HYBRID])
def test_explicit_route_uses_available_capability_without_online_router(route):
    gateway = Mock()
    gateway.generate_structured.side_effect = AssertionError("No routing request allowed")
    pipeline = FakePipeline()
    service = DatasetChatService(
        QueryRouter(gateway),
        pipeline if route != RouteLabel.RAG else None,
        pipeline if route != RouteLabel.SQL else None,
        pipeline if route == RouteLabel.HYBRID else None,
    )
    result = service.chat(f"/{route.lower()} Câu hỏi có nguồn được chọn rõ")
    assert result.route == route
    gateway.generate_structured.assert_not_called()


def test_hybrid_cannot_silently_downgrade_to_sql_when_documents_absent():
    gateway, pipeline = Mock(), Mock()
    result = DatasetChatService(QueryRouter(gateway), pipeline, None, None).chat("/hybrid KPI?")
    assert result.route == RouteLabel.UNSUPPORTED
    pipeline.run.assert_not_called()
    gateway.generate_structured.assert_not_called()


def test_ambiguous_natural_question_keeps_semantic_router_and_provider_cause():
    gateway = Mock()
    gateway.generate_structured.side_effect = ProviderError("Unavailable")
    pipeline = Mock()
    service = DatasetChatService(QueryRouter(gateway), pipeline, pipeline, pipeline)
    with pytest.raises(ProviderError):
        service.chat("Những nơi nào cần xem xét theo chính sách?")
    pipeline.run.assert_not_called()
    gateway.generate_structured.assert_called_once()


def test_empty_allowed_routes_do_not_expand_to_other_capabilities():
    gateway = Mock()
    result = QueryRouter(gateway).route("/sql count", frozenset())
    assert result.route == RouteLabel.UNSUPPORTED
    gateway.generate_structured.assert_not_called()
