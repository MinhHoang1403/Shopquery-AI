"""Category aggregation must not silently become per-entity aggregation."""

from dataclasses import replace

import pytest

from app.core.errors import SqlUnsupportedError, SqlValidationError
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.plan_binding import bind_approved_grain
from app.text_to_sql.query_plan import PlanExpression, PlanField, QueryPlan
from tests.test_plan_binding import setup_plan
from tests.test_query_compiler import field, source


def category_plan():
    context, compiler, _ = setup_plan()
    plan = QueryPlan(
        source=source(compiler, "payments"),
        fields=[
            PlanField(reference=field(compiler, "courses", "title"), alias="category"),
            PlanField(reference="e0", alias="total"),
        ],
        expressions=[
            PlanExpression(operation="sum", arguments=[field(compiler, "payments", "amount")])
        ],
        group_by=[field(compiler, "courses", "title")],
        grouping="category",
    )
    return context, compiler, plan


def test_explicit_category_grain_preserves_groups_and_projection():
    _, compiler, plan = category_plan()
    bound = bind_approved_grain(plan, compiler.references)
    assert bound.group_by == plan.group_by and bound.fields == plan.fields
    assert len(bound.relationships) == 2
    compiled = compiler.compile(bound)
    assert (
        "GROUP BY" in compiled.validated.statement
        and "SUM(" in compiled.validated.statement.upper()
    )
    assert "course_id" not in compiled.validated.statement.split("GROUP BY", 1)[1]


def test_category_mode_cannot_project_entity_key_or_ungrouped_dimension():
    _, compiler, plan = category_plan()
    key = field(compiler, "courses", "course_id")
    for modified in (
        plan.model_copy(
            update={"fields": [PlanField(reference=key, alias="entity"), plan.fields[1]]}
        ),
        plan.model_copy(
            update={
                "fields": [*plan.fields, PlanField(reference=key, alias="entity")],
                "group_by": [*plan.group_by, key],
            }
        ),
    ):
        with pytest.raises(SqlValidationError):
            compiler.compile(bind_approved_grain(modified, compiler.references))


def test_default_entity_grain_still_includes_approved_identity():
    _, compiler, plan = category_plan()
    bound = bind_approved_grain(plan.model_copy(update={"grouping": "entity"}), compiler.references)
    assert field(compiler, "courses", "course_id") in bound.group_by


def test_category_scope_never_changes_ambiguous_path_or_fact_measure_guards():
    from tests.test_three_table_join import PC

    context, _, plan = category_plan()
    compiler = QueryCompiler(replace(context, approved_joins=(*context.approved_joins, PC)))
    with pytest.raises(SqlUnsupportedError):
        bind_approved_grain(plan, compiler.references)


@pytest.mark.parametrize(
    "updates,branch",
    [
        ({"source": "unknown"}, "unknown_source"),
        ({"relationships": ["unknown"]}, "unknown_relationship"),
        ({"relationships": ["r0", "r0"]}, "duplicate_relationship"),
        ({"group_by": ["t0.invalid"]}, "unknown_reference"),
    ],
)
def test_binding_rejection_branch_is_bounded_and_does_not_remap_unknown_ids(updates, branch):
    _, compiler, plan = category_plan()
    with pytest.raises(SqlValidationError) as caught:
        bind_approved_grain(plan.model_copy(update=updates), compiler.references)
    assert caught.value.error_context.validation_branch == branch
    assert caught.value.error_context.origin_stage == "plan_binding"
