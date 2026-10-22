from dataclasses import replace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.core.errors import SqlUnsupportedError, SqlValidationError
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.query_plan import (
    PlanDecision,
    PlanExpression,
    PlanField,
    PlanFilter,
    QueryPlan,
)
from tests.test_query_compiler import field, source
from tests.test_three_table_join import PS, SC, TYPES
from tests.test_workspace_prompts import tuition_context


@pytest.mark.parametrize(
    "payload",
    [
        {"sql": "SELECT 1"},
        {"plan": None},
        {
            "plan": {"source": "t0", "fields": [{"alias": "n", "aggregate": "row_count"}]},
            "unsupported_reason": "both outcomes",
        },
    ],
)
def test_plan_decision_has_exactly_one_typed_outcome(payload):
    with pytest.raises(ValidationError):
        PlanDecision.model_validate(payload)


@pytest.mark.parametrize(
    "nodes",
    [
        [{"operation": "execute", "arguments": ["DROP TABLE x"]}],
        [{"operation": "add", "arguments": ["e0", "t0.c0"]}],
        [{"operation": "row_count"}] * 81,
    ],
)
def test_invalid_operator_cycle_and_node_bounds(nodes):
    with pytest.raises(ValidationError):
        QueryPlan(
            source="t0", fields=[PlanField(alias="n", aggregate="row_count")], expressions=nodes
        )


def test_reused_boolean_nodes_cannot_expand_exponentially():
    with pytest.raises(ValidationError, match="expansion"):
        QueryPlan(
            source="t0",
            fields=[PlanField(alias="n", aggregate="row_count")],
            expressions=[
                PlanExpression(operation="literal", value="1", value_type="NUMERIC"),
                PlanExpression(operation="eq", arguments=["t0.c0", "e0"]),
                PlanExpression(operation="and", arguments=["e1"] * 100),
                PlanExpression(operation="or", arguments=["e2"] * 100),
            ],
        )


@pytest.mark.parametrize(
    "operation,arguments,value_type,value",
    [
        ("literal", [], "NUMERIC", "NaN"),
        ("literal", [], "BIGINT", "9223372036854775808"),
        ("literal", [], "BOOLEAN", "yes"),
        ("literal", [], "TIMESTAMP", "2026-01-01T00:00:00+07:00"),
        ("literal", [], "TIMESTAMPTZ", "2026-01-01T00:00:00"),
        ("add", ["t0.c0", "t0.c2"], None, None),
        ("and", ["t0.c0", "t0.c1"], None, None),
        ("avg", ["t0.c2"], None, None),
    ],
)
def test_type_errors_stop_before_guard_execution_and_answer(
    operation, arguments, value_type, value
):
    plan = QueryPlan(
        source="t0",
        expressions=[
            PlanExpression(
                operation=operation,
                arguments=arguments,
                value_type=value_type,
                value=value,
            )
        ],
        fields=[PlanField(reference="e0", alias="x")],
    )
    planner, executor, gateway, guard = Mock(), Mock(), Mock(), Mock()
    planner.generate.return_value = plan
    with pytest.raises(SqlValidationError):
        TextToSqlPipeline(planner, QueryCompiler(tuition_context()), executor, gateway, guard).run(
            "Q"
        )
    guard.assert_not_called()
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()


@pytest.mark.parametrize("operation", ["sum", "avg", "min", "max"])
def test_plan_cannot_move_join_metric_to_dimension(operation):
    context = replace(
        tuition_context(),
        table_columns={t: set(c) for t, c in TYPES.items()},
        column_types=TYPES,
        allowed_schemas={t: "uploaded_data" for t in TYPES},
        approved_joins=(PS, SC),
    )
    compiler = QueryCompiler(context)
    plan = QueryPlan(
        source=source(compiler, "payments"),
        relationships=list(compiler.references.relationships),
        fields=[
            PlanField(
                reference=field(compiler, "courses", "fee"), aggregate=operation, alias="metric"
            )
        ],
    )
    with pytest.raises(SqlUnsupportedError):
        compiler.compile(plan)


def test_aggregate_and_group_grain_are_checked_before_postgres():
    compiler = QueryCompiler(tuition_context())
    identity = field(compiler, "tuition_fixture", "ma_hoc_vien")
    with pytest.raises(SqlValidationError, match="grouping grain"):
        compiler.compile(
            QueryPlan(
                source="t0",
                fields=[
                    PlanField(reference=identity, alias="id"),
                    PlanField(alias="n", aggregate="row_count"),
                ],
            )
        )
    with pytest.raises(SqlValidationError, match="Count aliases"):
        compiler.compile(
            QueryPlan(
                source="t0",
                fields=[
                    PlanField(
                        reference=field(compiler, "tuition_fixture", "da_dong"),
                        alias="matched_row_count",
                        aggregate="sum",
                    ),
                ],
            )
        )


@pytest.mark.parametrize("structured", [False, True])
def test_temporal_filters_cannot_compare_formatted_strings(structured):
    context = replace(
        tuition_context(),
        table_columns={"tuition_fixture": {"instant"}},
        column_types={"tuition_fixture": {"instant": "TIMESTAMPTZ"}},
    )
    nodes = [PlanExpression(operation="month_label", arguments=["t0.c0"])]
    if structured:
        nodes += [
            PlanExpression(operation="literal", value="2026-10", value_type="TEXT"),
            PlanExpression(operation="gte", arguments=["e0", "e1"]),
        ]
    plan = QueryPlan(
        source="t0",
        fields=[PlanField(alias="n", aggregate="row_count")],
        expressions=nodes,
        where="e2" if structured else None,
        filters=[]
        if structured
        else [PlanFilter(reference="e0", operator="gte", values=["2026-10"])],
    )
    with pytest.raises(SqlValidationError):
        QueryCompiler(context).compile(plan)
