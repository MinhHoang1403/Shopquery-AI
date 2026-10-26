"""Planning outcomes remain distinguishable without logging model statements."""

import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.diagnostics import diagnostic_request
from app.core.errors import ErrorContext, ProviderError, SqlUnsupportedError, SqlValidationError
from app.datasets.context import DatasetSqlContext
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.query_plan import PlanDecision, PlanField, QueryPlan
from tests.test_workspace_prompts import tuition_context


def pipeline(context, decision):
    gateway = SimpleNamespace(
        model_id="inetcloud-knowledge", generate_structured=Mock(return_value=decision)
    )
    compiler, executor = Mock(), Mock()
    service = TextToSqlPipeline(
        QueryPlanner(gateway, "2026-10-26", context), compiler, executor, gateway
    )
    return service, gateway, compiler, executor


def test_unsupported_outcome_retains_safe_reason_and_catalog_before_execution(caplog):
    context = tuition_context()
    service, gateway, compiler, executor = pipeline(
        context, PlanDecision(unsupported_reason="PRIVATE token=secret user@example.org")
    )
    with diagnostic_request() as trace, pytest.raises(SqlUnsupportedError) as error:
        service.run("PRIVATE question")
    metadata = error.value.error_context
    assert metadata.origin_stage == "sql_plan_generation"
    assert metadata.reason_code == "model_unsupported"
    assert metadata.model_reason_sha256 == hashlib.sha256(
        b"PRIVATE token=secret user@example.org"
    ).hexdigest()
    assert metadata.response_outcome == "unsupported"
    assert metadata.model_id == "inetcloud-knowledge"
    assert metadata.catalog_table_count == len(context.table_columns)
    assert metadata.catalog_column_count == sum(map(len, context.table_columns.values()))
    assert metadata.approved_relationship_count == len(context.approved_joins)
    assert metadata.correlation_id == trace.correlation_id
    assert error.value.code == "generator_unsupported"
    assert "PRIVATE" not in metadata.model_dump_json() + str(trace.events) + caplog.text
    assert "secret" not in str(trace.events)
    assert gateway.generate_structured.call_count == 1
    compiler.compile.assert_not_called()
    executor.execute.assert_not_called()


def test_empty_catalog_is_distinguished_before_provider():
    context = DatasetSqlContext("", {}, {})
    service, gateway, compiler, executor = pipeline(context, None)
    with diagnostic_request(), pytest.raises(SqlUnsupportedError) as error:
        service.run("Q")
    assert error.value.error_context.reason_code == "catalog_missing"
    gateway.generate_structured.assert_not_called()
    compiler.compile.assert_not_called()
    executor.execute.assert_not_called()


def test_success_and_backend_refusal_are_not_called_model_unsupported():
    context = tuition_context()
    decision = PlanDecision(
        plan=QueryPlan(source="t0", fields=[PlanField(reference="t0.c0", alias="x")])
    )
    service, _, compiler, executor = pipeline(context, decision)
    compiler.compile.side_effect = SqlUnsupportedError("Unsafe source", code="join_relationship")
    with diagnostic_request() as trace, pytest.raises(SqlUnsupportedError) as error:
        service.run("Q")
    assert error.value.code == "join_relationship"
    assert trace.facts["response_outcome"] == "query"
    assert any(
        e["stage"] == "sql_plan_generation" and e["status"] == "success" for e in trace.events
    )
    assert not any(e["stage"] == "generator_unsupported" for e in trace.events)
    executor.execute.assert_not_called()


@pytest.mark.parametrize("category", ["timeout", "wire_validation", "contract_conversion"])
def test_provider_failures_keep_category_and_neutral_planning_stage(category):
    service, gateway, compiler, executor = pipeline(tuition_context(), None)
    gateway.generate_structured.side_effect = ProviderError(
        "Private detail", error_context=ErrorContext(provider="knowledge", error_category=category)
    )
    with diagnostic_request(), pytest.raises(ProviderError) as error:
        service.run("Q")
    assert error.value.error_context.origin_stage == "sql_plan_generation"
    assert error.value.error_context.error_category == category
    assert error.value.error_context.model_id == "inetcloud-knowledge"
    assert error.value.error_context.catalog_table_count == len(tuition_context().table_columns)
    assert error.value.error_context.reason_code is None
    compiler.compile.assert_not_called()
    executor.execute.assert_not_called()


def test_valid_wire_query_can_fail_binding_without_a_model_unsupported_outcome():
    from tests.test_plan_binding import setup_plan

    context, _, plan = setup_plan()
    invalid = plan.model_copy(update={"source": "unknown_source"})
    service, _, compiler, executor = pipeline(context, PlanDecision(plan=invalid))
    with diagnostic_request() as trace, pytest.raises(SqlValidationError) as error:
        service.run("Q")
    assert not isinstance(error.value, SqlUnsupportedError)
    assert error.value.error_context.response_outcome == "query"
    assert error.value.error_context.reason_code is None
    assert trace.facts["response_outcome"] == "query"
    compiler.compile.assert_not_called()
    executor.execute.assert_not_called()
