import pytest

from app.core.errors import SqlValidationError
from app.text_to_sql.plan_binding import bind_approved_grain
from app.text_to_sql.query_plan import PlanExpression
from tests.test_plan_binding import setup_plan
from tests.test_query_compiler import field


def test_captured_failure_class_missing_projected_attribute_group_is_explicit():
    _, compiler, plan = setup_plan()
    identity = field(compiler, "courses", "course_id")
    invalid = plan.model_copy(update={"group_by": [identity]})
    bound = bind_approved_grain(invalid, compiler.references)
    with pytest.raises(SqlValidationError) as caught:
        compiler.compile(bound)
    assert caught.value.error_context.validation_branch == "projection_grain"
    assert caught.value.error_context.origin_stage == "plan_compilation"
    assert "courses" not in caught.value.error_context.model_dump_json()
    valid = bound.model_copy(update={"group_by": [identity, plan.fields[0].reference]})
    assert compiler.compile(valid).validated.fact_table == "payments"


@pytest.mark.parametrize("where,having", [("e99", None), (None, "e99")])
def test_binding_covers_predicate_references(where, having):
    _, compiler, plan = setup_plan()
    with pytest.raises(SqlValidationError) as caught:
        bind_approved_grain(
            plan.model_copy(update={"where": where, "having": having}), compiler.references
        )
    assert caught.value.error_context.validation_branch == "unknown_reference"


def test_arity_and_typed_value_failures_keep_distinct_safe_compiler_branches():
    _, compiler, plan = setup_plan()
    bad = plan.model_copy(
        update={"expressions": [PlanExpression(operation="row_count", arguments=["t0.c0"])]}
    )
    with pytest.raises(SqlValidationError) as caught:
        compiler.compile(bad)
    assert caught.value.error_context.validation_branch == "expression_arity"
    with pytest.raises(SqlValidationError) as caught:
        compiler._value("PRIVATE_NOT_A_NUMBER", "NUMERIC")
    assert caught.value.error_context.validation_branch == "literal_value"
    assert "PRIVATE" not in caught.value.error_context.model_dump_json()
