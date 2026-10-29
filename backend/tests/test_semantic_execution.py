"""Exercise semantic dispatch through real compiler/policy binding, without providers."""

from dataclasses import replace
from unittest.mock import Mock
from uuid import UUID

import pytest

from app.core.errors import ModelResponseError
from app.routing.hybrid import HybridPipeline
from app.semantic.policy import bind_policy_task
from app.semantic.request import RequestIdentity, semantic_request
from app.semantic.task import SemanticTask
from tests.test_evidence_coverage import fixture, pipeline


def task(selection="all"):
    return SemanticTask.model_validate(
        {
            "operation": "apply_policy",
            "question": "Assess units against the policy.",
            "population": {"grouping": "entity"},
            "output": {"classification": selection},
            "policy": {"description": "Apply the documented unit policy."},
        }
    )


@pytest.mark.parametrize("selection", ["all", "qualified", "not_qualified"])
def test_semantic_hybrid_uses_bound_task_and_no_second_plan_or_verdict(selection):
    chunk, context, _ = fixture()
    owner = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")
    context = replace(context, dataset_id=71, owner_user_id=owner, table_row_counts={"random_d": 3})
    chunk = replace(
        chunk, document_scope=replace(chunk.document_scope, dataset_id=71, owner_user_id=owner)
    )
    rows = [
        {"entity_id": "U1", "metric_value": "40.00"},
        {"entity_id": "U2", "metric_value": "0.00"},
        {"entity_id": "U3", "metric_value": "39.999999999999999999999999999"},
    ]
    sql, executor, gateway = pipeline(context, rows)
    executor.execute.side_effect = [
        [{"entity_count": len(rows)}],
        [{"entity_id": row["entity_id"]} for row in rows],
        rows,
    ]
    hybrid = HybridPipeline(sql, Mock(retrieve=Mock(return_value=[chunk])), gateway, context)
    request = task(selection)
    with semantic_request(
        RequestIdentity(
            context.owner_user_id, None, context.dataset_id, request.question, "2026-10-29"
        )
    ):
        result = hybrid.run(request.question, task=request)
    assert result.verification_status == "verified_classification"
    assert (
        result.answer_row_indices
        == {"all": None, "qualified": (0,), "not_qualified": (1, 2)}[selection]
    )
    assert len(result.rows) == 3
    assert executor.execute.call_count == 3
    gateway.generate_structured.assert_not_called()


@pytest.mark.parametrize("mutation", ["source", "relationship", "unresolved"])
def test_policy_binding_never_overwrites_a_conflicting_task(mutation):
    chunk, context, _ = fixture()
    data = task().model_dump()
    if mutation == "source":
        data["population"]["source"] = "t0"
    elif mutation == "relationship":
        data["population"]["relationships"] = ["r99"]
    else:
        data["unresolved"] = ["Unbound date constraint"]
    with pytest.raises(ModelResponseError):
        bind_policy_task(SemanticTask.model_validate(data), [chunk], context)


@pytest.mark.parametrize(
    "direction,nulls,expected",
    [
        ("asc", "last", (1, 2, 0, 3)),
        ("desc", "last", (0, 2, 1, 3)),
        ("asc", "first", (3, 1, 2, 0)),
        ("desc", "first", (3, 0, 2, 1)),
    ],
)
def test_output_sort_is_decimal_lossless_and_null_position_is_independent(
    direction, nulls, expected
):
    from app.semantic.presentation import select_verified_rows
    from app.semantic.task import Ordering
    from app.text_to_sql.answer import ResultColumn

    output = task().output.model_copy(
        update={
            "ordering": (Ordering(field="metric_value", direction=direction, nulls=nulls),),
        }
    )
    rows = [{"metric_value": value} for value in ("40", "0", "39.999999999999999999999999", None)]
    columns = (ResultColumn(key="metric_value", label="Metric", data_type="NUMERIC"),)
    assert select_verified_rows(output, rows, ["qualified"] * 4, columns) == expected


def test_output_limit_is_after_classification_and_sorting():
    from app.semantic.presentation import select_verified_rows
    from app.semantic.task import Ordering
    from app.text_to_sql.answer import ResultColumn

    output = task("not_qualified").output.model_copy(
        update={
            "ordering": (Ordering(field="metric_value", direction="desc"),),
            "limit": 1,
        }
    )
    rows = [{"metric_value": value} for value in ("100", "0", "39.99")]
    columns = (ResultColumn(key="metric_value", label="Metric", data_type="NUMERIC"),)
    assert select_verified_rows(
        output, rows, ["qualified", "not_qualified", "not_qualified"], columns
    ) == (2,)


@pytest.mark.parametrize("change", ["owner", "dataset", "types", "relations", "values"])
def test_request_catalog_changes_cannot_be_rebound(change):
    from app.semantic.request import bind_request

    _, context, _ = fixture()
    owner = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")
    context = replace(context, dataset_id=71, owner_user_id=owner)
    changed = {
        "owner": replace(context, owner_user_id=UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93643")),
        "dataset": replace(context, dataset_id=72),
        "types": replace(context, column_types={}),
        "relations": replace(context, approved_joins=()),
        "values": replace(context, categorical_values={"random_d": {"name": ("A",)}}),
    }[change]
    with semantic_request(RequestIdentity(owner, None, 71, task().question, "2026-10-29")):
        bind_request(context, ("query",))
        with pytest.raises(ModelResponseError):
            bind_request(changed, ("query",))
    # A new request can legitimately bind a new revision; no cross-request leak.
    if change not in {"owner", "dataset"}:
        with semantic_request(RequestIdentity(owner, None, 71, task().question, "2026-10-29")):
            assert bind_request(changed, ("query",)) is not None


@pytest.mark.parametrize("selection", ["all", "qualified", "not_qualified"])
@pytest.mark.parametrize("column", ["name", "ref_unit"])
def test_entity_population_filter_survives_both_universe_and_metric_reads(selection, column):
    from app.semantic.task import Predicate, ScalarValue
    from app.text_to_sql.compiler import SchemaReferences

    chunk, context, _ = fixture()
    owner = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")
    context = replace(context, dataset_id=71, owner_user_id=owner, table_row_counts={"random_d": 3})
    chunk = replace(
        chunk, document_scope=replace(chunk.document_scope, dataset_id=71, owner_user_id=owner)
    )
    reference = next(
        key
        for key, location in SchemaReferences.from_context(context).columns.items()
        if location == ("random_d", column)
    )
    request = task(selection)
    request = request.model_copy(
        update={
            "population": request.population.model_copy(
                update={
                    "predicates": Predicate(
                        reference=reference,
                        operator="eq",
                        values=(ScalarValue(data_type="TEXT", value="A"),),
                    ),
                }
            )
        }
    )
    rows = [
        {"entity_id": "U1", "metric_value": "40.00"},
        {"entity_id": "U2", "metric_value": "0.00"},
    ]
    sql, executor, gateway = pipeline(context, rows)
    executor.execute.side_effect = [
        [{"entity_count": 2}],
        [{"entity_id": "U1"}, {"entity_id": "U2"}],
        rows,
    ]
    with semantic_request(RequestIdentity(owner, None, 71, request.question, "2026-10-29")):
        result = HybridPipeline(
            sql, Mock(retrieve=Mock(return_value=[chunk])), gateway, context
        ).run(request.question, task=request)
    assert result.verification_status == "verified_classification"
    assert executor.execute.call_count == 3
    for call in executor.execute.call_args_list:
        assert "WHERE" in call.args[0].statement
        assert "A" in call.args[1].values()
    gateway.generate_structured.assert_not_called()


@pytest.mark.parametrize(
    "failure", ["missing_fact", "duplicate_identity", "truncated_universe", "stale_count"]
)
def test_universe_mismatch_never_returns_verified_classification(failure):
    chunk, context, _ = fixture()
    owner = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")
    context = replace(context, dataset_id=71, owner_user_id=owner, table_row_counts={"random_d": 2})
    chunk = replace(
        chunk, document_scope=replace(chunk.document_scope, dataset_id=71, owner_user_id=owner)
    )
    rows = [
        {"entity_id": "U1", "metric_value": "40.00"},
        {"entity_id": "U2", "metric_value": "0.00"},
    ]
    ids = [{"entity_id": "U1"}, {"entity_id": "U2"}]
    if failure == "missing_fact":
        rows = rows[:1]
    if failure == "duplicate_identity":
        rows[1]["entity_id"] = "U1"
    if failure == "truncated_universe":
        ids = ids[:1]
    sql, executor, gateway = pipeline(context, rows)
    executor.execute.side_effect = [
        [{"entity_count": 3 if failure == "stale_count" else 2}],
        ids,
        rows,
    ]
    with (
        semantic_request(RequestIdentity(owner, None, 71, task().question, "2026-10-29")),
        pytest.raises(ModelResponseError),
    ):
        HybridPipeline(sql, Mock(retrieve=Mock(return_value=[chunk])), gateway, context).run(
            task().question, task=task()
        )
    gateway.generate_structured.assert_not_called()


@pytest.mark.parametrize("pipeline_kind", ["sql", "hybrid"])
def test_authenticated_dispatch_cannot_reenter_the_legacy_resolver(pipeline_kind):
    chunk, context, _ = fixture()
    sql, executor, gateway = pipeline(context, [])
    rag = Mock(retrieve=Mock(return_value=[chunk]))
    selected = sql if pipeline_kind == "sql" else HybridPipeline(sql, rag, gateway, context)
    with (
        semantic_request(
            RequestIdentity(
                UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642"),
                None,
                71,
                task().question,
                "2026-10-29",
            )
        ),
        pytest.raises(ModelResponseError),
    ):
        selected.run(task().question)
    executor.execute.assert_not_called()
    gateway.generate_structured.assert_not_called()
    rag.retrieve.assert_not_called()


def test_later_planning_stages_cannot_expand_the_first_server_capabilities():
    from app.semantic.request import bind_request

    _, context, _ = fixture()
    owner = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")
    context = replace(context, dataset_id=71, owner_user_id=owner)
    with semantic_request(RequestIdentity(owner, None, 71, task().question, "2026-10-29")):
        assert bind_request(context, ("query",)).authorized_capabilities == ("query",)
        assert bind_request(context, ("query", "apply_policy")).authorized_capabilities == (
            "query",
        )
    with semantic_request(RequestIdentity(owner, None, 71, task().question, "2026-10-29")):
        assert bind_request(context, ("apply_policy",)).authorized_capabilities == ("apply_policy",)


@pytest.mark.parametrize("persistent", [False, True])
def test_guest_request_is_explicitly_temporary_without_a_fake_authenticated_owner(persistent):
    from uuid import uuid4

    from app.semantic.request import bind_request

    _, context, _ = fixture()
    context = replace(
        context,
        dataset_id=0,
        owner_user_id=None,
        allowed_schemas={
            table: "uploaded_data" if persistent else "pg_temp" for table in context.table_columns
        },
    )
    with semantic_request(
        RequestIdentity(
            None,
            None,
            0,
            task().question,
            "2026-10-29",
            principal="guest",
            guest_request_id=uuid4(),
        )
    ):
        if persistent:
            with pytest.raises(ModelResponseError):
                bind_request(context, ("query",))
        else:
            request = bind_request(context, ("query",))
            assert request.principal == "guest" and request.owner_user_id is None
