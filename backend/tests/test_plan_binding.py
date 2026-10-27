from dataclasses import replace

import pytest

from app.core.diagnostics import diagnostic_request
from app.core.errors import SqlUnsupportedError, SqlValidationError
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.plan_binding import bind_approved_grain
from app.text_to_sql.query_plan import PlanExpression, PlanField, QueryPlan
from tests.test_query_compiler import field, source
from tests.test_three_table_join import PC, PS, SC, TYPES
from tests.test_workspace_prompts import tuition_context


def setup_plan():
    context = replace(
        tuition_context(),
        table_columns={t: set(c) for t, c in TYPES.items()},
        column_types=TYPES,
        allowed_schemas={t: "uploaded_data" for t in TYPES},
        approved_joins=(PS, SC),
    )
    compiler = QueryCompiler(context)
    plan = QueryPlan(
        source=source(compiler, "courses"),
        fields=[
            PlanField(reference=field(compiler, "courses", "title"), alias="name"),
            PlanField(reference="e0", alias="total"),
            PlanField(reference="e1", alias="fact_row_count"),
        ],
        expressions=[
            PlanExpression(operation="sum", arguments=[field(compiler, "payments", "amount")]),
            PlanExpression(operation="row_count"),
        ],
        group_by=[field(compiler, "courses", "title")],
    )
    return context, compiler, plan


def test_unique_fact_path_and_stable_group_key_come_from_approved_metadata():
    _, compiler, plan = setup_plan()
    bound = bind_approved_grain(plan, compiler.references)
    compiled = compiler.compile(bound)
    assert bound.source == source(compiler, "payments")
    assert field(compiler, "courses", "course_id") in bound.group_by
    assert set(compiled.validated.relationship_ids) == {PS.relationship_id, SC.relationship_id}
    assert compiled.validated.fact_table == "payments"
    assert compiled.validated.count_metrics[0].kind.value == "row_count"
    assert plan.source != bound.source  # Input remains immutable evidence.


def test_explicit_approved_identity_completes_its_projected_dimension_attribute():
    _, compiler, plan = setup_plan()
    identity = field(compiler, "courses", "course_id")
    name = plan.fields[0].reference
    plan = plan.model_copy(update={"group_by": [identity]})
    bound = bind_approved_grain(plan, compiler.references)
    assert bound.group_by == [identity, name]
    assert plan.group_by == [identity]
    assert compiler.compile(bound).validated.fact_table == "payments"


@pytest.mark.parametrize("table,column", [("students", "course_id"), ("payments", "student_id")])
def test_foreign_key_group_is_not_guessed_as_the_requested_dimension_grain(table, column):
    _, compiler, plan = setup_plan()
    identity = field(compiler, table, column)
    bound = bind_approved_grain(
        plan.model_copy(update={"group_by": [identity]}), compiler.references
    )
    assert identity in bound.group_by
    assert plan.fields[0].reference not in bound.group_by
    with pytest.raises(SqlValidationError):
        compiler.compile(bound)


@pytest.mark.parametrize(
    "case", ["category", "missing_identity", "fact_attribute", "same_name_unapproved_key"]
)
def test_group_completion_does_not_guess_a_different_grain(case):
    _, compiler, plan = setup_plan()
    identity = field(compiler, "courses", "course_id")
    updates = {"group_by": [identity]}
    if case == "category":
        updates["grouping"] = "category"
    elif case == "missing_identity":
        updates["group_by"] = []
    elif case == "same_name_unapproved_key":
        updates["group_by"] = [field(compiler, "payments", "course_id")]
    else:
        updates["fields"] = [
            *plan.fields,
            PlanField(reference=field(compiler, "payments", "amount"), alias="raw_amount"),
        ]
    bound = bind_approved_grain(plan.model_copy(update=updates), compiler.references)
    with pytest.raises((SqlValidationError, SqlUnsupportedError)):
        compiler.compile(bound)


def test_compiler_still_rejects_wrong_fact_without_backend_binding():
    _, compiler, plan = setup_plan()
    with pytest.raises(SqlUnsupportedError) as error:
        compiler.compile(
            plan.model_copy(update={"relationships": list(compiler.references.relationships)})
        )
    assert error.value.grain_reason == "fact_source"


def test_unknown_or_duplicate_relationship_never_becomes_an_inferred_join():
    _, compiler, plan = setup_plan()
    for relationships in (["unknown"], ["r0", "r0"]):
        with pytest.raises(SqlValidationError):
            bind_approved_grain(
                plan.model_copy(update={"relationships": relationships}), compiler.references
            )


def test_missing_path_refuses_instead_of_using_a_partial_join():
    context, _, plan = setup_plan()
    compiler = QueryCompiler(replace(context, approved_joins=(SC,)))
    with pytest.raises(SqlUnsupportedError, match="No unique"):
        bind_approved_grain(plan, compiler.references)


def test_direct_and_indirect_approved_paths_are_not_silently_disambiguated():
    context, _, plan = setup_plan()
    compiler = QueryCompiler(replace(context, approved_joins=(PS, SC, PC)))
    with pytest.raises(SqlUnsupportedError, match="No unique"):
        bind_approved_grain(plan, compiler.references)


def test_row_count_alone_does_not_reinterpret_a_dimension_as_orders():
    _, compiler, plan = setup_plan()
    plan = plan.model_copy(
        update={
            "expressions": [PlanExpression(operation="row_count")],
            "fields": [plan.fields[0], PlanField(reference="e0", alias="fact_row_count")],
        }
    )
    bound = bind_approved_grain(plan, compiler.references)
    assert bound.source == plan.source and not bound.relationships


def test_dimension_measure_does_not_change_an_explicit_fact_into_a_different_query():
    _, compiler, plan = setup_plan()
    plan = plan.model_copy(
        update={
            "source": source(compiler, "payments"),
            "expressions": [
                PlanExpression(operation="sum", arguments=[field(compiler, "courses", "fee")]),
                PlanExpression(operation="row_count"),
            ],
        }
    )
    with pytest.raises(SqlUnsupportedError, match="No unique"):
        bind_approved_grain(plan, compiler.references)


def test_compiler_grain_failure_has_a_precise_private_data_free_reason():
    from unittest.mock import Mock

    _, compiler, plan = setup_plan()
    plan = plan.model_copy(update={"relationships": list(compiler.references.relationships)})
    executor, gateway = Mock(), Mock()
    pipeline = TextToSqlPipeline(
        Mock(generate=Mock(return_value=plan)), compiler, executor, gateway
    )
    with diagnostic_request() as trace, pytest.raises(SqlUnsupportedError):
        pipeline.run("Do not log this question")
    failures = [event for event in trace.events if event["status"] == "failure"]
    assert any(
        event["stage"] == "join_grain" and event["reason"] == "fact_source" for event in failures
    )
    assert "Do not log" not in str(trace.events)
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()
