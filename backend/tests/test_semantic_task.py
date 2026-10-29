"""Contract regression without a provider, database or changes to the locked holdout."""

from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.semantic.coverage import require_evidence, verify_coverage
from app.semantic.planning import task_query_plan
from app.semantic.task import RequestContext, ScalarValue, SemanticTask


def specification(operation="query"):
    result = {
        "operation": operation,
        "question": "Tổng giá trị tháng trước ở miền Bắc; chỉ lấy hai nhóm thấp nhất.",
        "population": {
            "source": "t0",
            "grouping": "entity",
            "group_by": ["t0.c0"],
            "predicates": {
                "kind": "all",
                "children": [
                    {
                        "reference": "t0.c1",
                        "kind": "comparison",
                        "operator": "eq",
                        "values": [{"data_type": "TEXT", "value": "Bắc"}],
                    },
                    {
                        "reference": "t0.c2",
                        "kind": "comparison",
                        "operator": "gte",
                        "values": [{"data_type": "DATE", "value": "2032-09-01"}],
                    },
                    {
                        "reference": "t0.c2",
                        "kind": "comparison",
                        "operator": "lt",
                        "values": [{"data_type": "DATE", "value": "2032-10-01"}],
                    },
                ],
            },
        },
        "output": {
            "fields": [
                {"reference": "t0.c0", "alias": "entity"},
                {"reference": "t0.c3", "alias": "total", "aggregate": "sum"},
            ],
            "ordering": [{"field": "total", "direction": "asc"}],
            "limit": 2,
            "classification": "none" if operation == "query" else "not_qualified",
        },
    }
    if operation == "apply_policy":
        result["policy"] = {"description": "Quy định của workspace", "metric": "total"}
    return result


def request(task):
    return RequestContext(
        owner_user_id=uuid4(),
        conversation_id=uuid4(),
        dataset_id=13,
        catalog_revision="a" * 64,
        question=task.question,
        reference_date="2032-10-25",
        time_zone="Asia/Ho_Chi_Minh",
    )


def test_lowering_preserves_population_and_output_separately():
    task = SemanticTask.model_validate(specification())
    plan = task_query_plan(task)
    assert plan.group_by == ["t0.c0"] and plan.limit == 2
    assert plan.sort[0].field == "total" and plan.sort[0].direction == "asc"
    comparisons = [e for e in plan.expressions if e.operation in {"eq", "gte", "lt"}]
    assert [e.operation for e in comparisons] == ["eq", "gte", "lt"]
    assert [e.value for e in plan.expressions if e.operation == "literal"] == [
        "Bắc",
        "2032-09-01",
        "2032-10-01",
    ]
    context = request(task)
    verify_coverage(require_evidence(context, task), context, task, plan)


@pytest.mark.parametrize("mutation", ["where", "group", "order", "limit", "predicate", "source"])
def test_dropped_or_changed_requirement_cannot_pass_coverage(mutation):
    task = SemanticTask.model_validate(specification())
    context = request(task)
    plan = task_query_plan(task)
    if mutation == "where":
        plan = plan.model_copy(update={"where": None})
    elif mutation == "predicate":
        nodes = list(plan.expressions)
        nodes[-2] = nodes[-2].model_copy(update={"operation": "gte"})
        plan = plan.model_copy(update={"expressions": nodes})
    else:
        key, value = {
            "group": ("group_by", []),
            "order": ("sort", []),
            "limit": ("limit", None),
            "source": ("source", "t1"),
        }[mutation]
        plan = plan.model_copy(update={key: value})
    with pytest.raises(ValueError, match="preserve"):
        verify_coverage(require_evidence(context, task), context, task, plan)


def test_policy_selection_order_limit_do_not_filter_input_sql():
    task = SemanticTask.model_validate(specification("apply_policy"))
    plan = task_query_plan(task)
    assert plan.where is not None  # User population survives.
    assert plan.limit is None and not plan.sort  # Output selection is after verification.
    assert task.output.limit == 2 and task.output.classification == "not_qualified"
    assert task.policy.metric == "total"


@pytest.mark.parametrize("field", ["owner_user_id", "conversation_id", "dataset_id", "question"])
def test_requirement_cannot_cross_request_scope(field):
    task = SemanticTask.model_validate(specification())
    context = request(task)
    evidence = require_evidence(context, task)
    value = 99 if field == "dataset_id" else "Another question" if field == "question" else uuid4()
    with pytest.raises(ValueError):
        verify_coverage(
            evidence, context.model_copy(update={field: value}), task, task_query_plan(task)
        )


def test_router_classification_cannot_mint_or_override_evidence():
    task = SemanticTask.model_validate(specification("apply_policy"))
    context = request(task)
    evidence = require_evidence(context, task)
    changed = task.model_copy(
        update={
            "output": task.output.model_copy(update={"classification": "qualified"}),
        }
    )
    with pytest.raises(ValueError):
        verify_coverage(evidence, context, changed, task_query_plan(changed))
    with pytest.raises(ValidationError):
        SemanticTask.model_validate({**specification(), "verified": True})
    with pytest.raises(ValueError):
        verify_coverage(
            replace(evidence, sources=("documents",)), context, task, task_query_plan(task)
        )


def test_unresolved_or_unbound_policy_cannot_be_silently_ignored():
    data = specification()
    data["unresolved"] = ["Chưa xác định tháng kinh doanh"]
    task = SemanticTask.model_validate(data)
    with pytest.raises(ValueError):
        require_evidence(request(task), task)
    with pytest.raises(ValueError):
        task_query_plan(task)
    data = specification("apply_policy")
    data["policy"]["applicability"] = deepcopy(data["population"]["predicates"])
    with pytest.raises(ValueError, match="applicability"):
        task_query_plan(SemanticTask.model_validate(data))


@pytest.mark.parametrize(
    "data_type,value",
    [
        ("NUMERIC", "NaN"),
        ("NUMERIC", "Infinity"),
        ("BIGINT", "1.5"),
        ("BIGINT", "9223372036854775808"),
        ("BOOLEAN", "yes"),
        ("DATE", "2032-02-30"),
        ("TIMESTAMPTZ", "2032-09-01T00:00:00"),
        ("TIMESTAMP", "2032-09-01T00:00:00+07:00"),
    ],
)
def test_bad_literals_fail_locally(data_type, value):
    with pytest.raises(ValidationError):
        ScalarValue(data_type=data_type, value=value)


def test_disjunction_exact_decimal_and_null_predicate_are_preserved():
    data = specification()
    data["population"]["predicates"] = {
        "kind": "any",
        "children": [
            {"kind": "comparison", "reference": "t0.c3", "operator": "is_null"},
            {
                "kind": "comparison",
                "reference": "t0.c3",
                "operator": "eq",
                "values": [{"data_type": "NUMERIC", "value": "9007199254740993.00001"}],
            },
        ],
    }
    plan = task_query_plan(SemanticTask.model_validate(data))
    assert plan.expressions[-1].operation == "or"
    assert any(e.value == "9007199254740993.00001" for e in plan.expressions)
    assert any(e.operation == "is_null" and e.arguments == ["t0.c3"] for e in plan.expressions)


def test_policy_only_task_has_no_table_execution_requirement():
    task = SemanticTask(operation="explain", question="Quy định này yêu cầu gì?")
    assert require_evidence(request(task), task).sources == ("documents",)
    with pytest.raises(ValueError):
        task_query_plan(task)
