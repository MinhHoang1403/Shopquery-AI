import json

import pytest

from app.database.guest_access import configure_guest_access
from app.database.session import get_setup_engine
from app.dependencies import _build_chat_service, _build_dataset_chat_service
from app.guest.pipeline import run_guest_chat
from app.guest.worker import parse_guest_file
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.query_plan import PlanDecision, PlanExpression, PlanField, QueryPlan
from tests.join_domains import DOMAINS
from tests.test_join_domains_integration import domain_workspace  # noqa: F401
from tests.test_plan_providers import gateway_harness, response
from tests.test_query_compiler import source

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize("domain_workspace", [(DOMAINS[0], 19)], indirect=True)
def test_real_provider_plan_through_authenticated_factory(monkeypatch, provider, domain_workspace):  # noqa: F811
    _, _, _, dataset, settings, context, facts = domain_workspace
    fact = dataset.tables[-1].physical_table_name
    compiler = QueryCompiler(context)
    decision = PlanDecision(
        plan=QueryPlan(
            source=source(compiler, fact), fields=[PlanField(alias="rows", aggregate="row_count")]
        )
    )
    responses = [
        response(
            provider,
            '{"route":"SQL","reason":"Rows","evidence_requirement":"tables","policy_intent":"none","policy_scope":"unspecified"}',
        ),
        response(provider, decision.model_dump_json()),
    ]
    gateway, calls = gateway_harness(monkeypatch, provider, responses)
    try:
        service = _build_dataset_chat_service(settings, context, gateway)
        result = service.chat("Count rows")
        assert result.rows == [{"rows": len(facts)}]
        assert isinstance(service._sql_pipeline._planner, QueryPlanner)
        assert isinstance(service._sql_pipeline._compiler, QueryCompiler)
        assert len(calls) == 2
        assert "GenerationDecision" in json.dumps(json.loads(calls[1].content))
    finally:
        gateway.close()


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_real_provider_plan_through_guest_factory(monkeypatch, provider):
    from app.core.config import get_settings

    settings = get_settings()
    configure_guest_access(get_setup_engine())
    file = parse_guest_file("numbers.csv", b'Amount\n10.25\n0.00\n""\n', None, settings)
    decision = PlanDecision(
        plan=QueryPlan(
            source="t0",
            expressions=[PlanExpression(operation="sum", arguments=["t0.c0"])],
            fields=[
                PlanField(reference="e0", alias="total"),
            ],
        )
    )
    responses = [
        response(
            provider,
            '{"route":"SQL","reason":"Rows","evidence_requirement":"tables","policy_intent":"none","policy_scope":"unspecified"}',
        ),
        response(provider, decision.model_dump_json()),
    ]
    gateway, calls = gateway_harness(monkeypatch, provider, responses)
    try:
        result = run_guest_chat([file], "Sum amount", settings, gateway=gateway)
        assert result.rows == [{"total": "10.25"}] and len(calls) == 2
    finally:
        gateway.close()


def test_default_factory_uses_same_plan_path_without_live_calls(monkeypatch):
    from unittest.mock import Mock

    from app.core.config import get_settings

    gateway = Mock()
    service = _build_chat_service(get_settings(), gateway)
    assert isinstance(service._sql_pipeline._planner, QueryPlanner)
    assert isinstance(service._sql_pipeline._compiler, QueryCompiler)
    assert service._hybrid_pipeline._sql_pipeline is service._sql_pipeline
    gateway.generate_structured.assert_not_called()
