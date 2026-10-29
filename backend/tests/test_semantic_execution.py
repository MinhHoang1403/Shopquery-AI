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


def test_combine_explanation_cannot_present_an_unrequested_policy_classification():
    from app.routing.hybrid_policy import complete_policy_evidence

    chunk, context, _ = fixture()
    owner = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")
    context = replace(context, dataset_id=71, owner_user_id=owner)
    chunk = replace(
        chunk, document_scope=replace(chunk.document_scope, dataset_id=71, owner_user_id=owner)
    )
    bound = bind_policy_task(task(), complete_policy_evidence([chunk]), context).task
    combined = SemanticTask.model_validate(
        {
            **bound.model_dump(),
            "operation": "combine",
            "policy": None,
            "output": {**bound.output.model_dump(), "classification": "none"},
        }
    )
    sql, executor, gateway = pipeline(context, [{"entity_id": "U1", "metric_value": "40.00"}])
    with semantic_request(RequestIdentity(owner, None, 71, combined.question, "2026-10-29")):
        result = HybridPipeline(
            sql, Mock(retrieve=Mock(return_value=[chunk])), gateway, context
        ).run(combined.question, task=combined)
    assert result.verification_status == "explanation"
    assert "Đạt: U1" not in result.answer and "Qualified: U1" not in result.answer
    gateway.generate_structured.assert_not_called()


def test_explicit_policy_plan_keeps_row_count_provenance_and_does_not_need_prose_metric_inference():
    from app.routing.hybrid_policy import complete_policy_evidence
    from app.semantic.task import OutputSelection, PolicyRequirement, Population, Projection
    from app.text_to_sql.compiler import SchemaReferences
    from tests.hybrid_fixtures import rule_block, scoped_chunk

    chunk, context, _ = fixture()
    chunk = scoped_chunk(41, "rule.md", "Policy", rule_block("ref_unit", "amount", "40.00"), 0.1)
    refs = SchemaReferences.from_context(context)
    identity = next(k for k, v in refs.columns.items() if v == ("random_d", "ref_unit"))
    amount = next(k for k, v in refs.columns.items() if v == ("random_f", "amount"))
    source = next(k for k, v in refs.tables.items() if v == "random_f")
    request = SemanticTask(
        operation="apply_policy",
        question=task().question,
        population=Population(source=source, grouping="entity", group_by=(identity,)),
        output=OutputSelection(
            fields=(
                Projection(reference=identity, alias="entity_id"),
                Projection(reference=amount, alias="total", aggregate="sum"),
                Projection(alias="fact_row_count", aggregate="row_count"),
            ),
            classification="all",
        ),
        policy=PolicyRequirement(description="Apply the saved rule", metric="total"),
    )
    bound = bind_policy_task(request, complete_policy_evidence([chunk]), context)
    assert bound.task.output.fields == request.output.fields
    assert bound.identity_field == "entity_id"


@pytest.mark.parametrize("mutation", ["metric", "fact_filter", "having", "applicability"])
def test_explicit_policy_task_does_not_gain_authority_from_valid_shape(mutation):
    from app.semantic.task import Predicate, ScalarValue

    chunk, context, _ = fixture()
    bound = bind_policy_task(task(), [chunk], context).task
    data = bound.model_dump()
    if mutation == "metric":
        data["output"]["fields"][1]["aggregate"] = "avg"
    elif mutation == "fact_filter":
        from app.text_to_sql.compiler import SchemaReferences

        reference = next(
            key
            for key, location in SchemaReferences.from_context(context).columns.items()
            if location == ("random_f", "amount")
        )
        data["population"]["predicates"] = Predicate(
            reference=reference,
            operator="gt",
            values=(ScalarValue(data_type="NUMERIC", value="0"),),
        ).model_dump()
    else:
        predicate = Predicate(
            reference=bound.output.fields[0].reference,
            operator="eq",
            values=(ScalarValue(data_type="TEXT", value="U1"),),
        ).model_dump()
        if mutation == "having":
            data["output"]["predicates"] = predicate
        else:
            data["policy"]["applicability"] = predicate
    with pytest.raises(ModelResponseError):
        bind_policy_task(SemanticTask.model_validate(data), [chunk], context)


def test_semantic_telemetry_is_enum_only_without_task_or_question_contents():
    from app.core.observability import safe_metadata

    assert safe_metadata(
        {
            "semantic_operation": "apply_policy",
            "coverage_status": "population_complete",
            "question": "PRIVATE",
            "task": {"source": "PRIVATE"},
        }
    ) == {"semantic_operation": "apply_policy", "coverage_status": "population_complete"}
    assert safe_metadata({"semantic_operation": "PRIVATE", "coverage_status": "PRIVATE"}) == {}


@pytest.mark.parametrize("mutation", ["where", "limit", "parameters", "evidence"])
def test_emitted_artifact_is_rechecked_against_the_scoped_task_before_execution(mutation):
    from app.semantic.coverage import prepare_task_plan, verify_compiled_task
    from app.semantic.task import Predicate, ScalarValue
    from app.text_to_sql.compiler import QueryCompiler

    chunk, context, _ = fixture()
    owner = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")
    context = replace(context, dataset_id=71, owner_user_id=owner)
    task_data = bind_policy_task(
        task(),
        [chunk],
        replace(
            context,
            dataset_id=chunk.document_scope.dataset_id,
            owner_user_id=chunk.document_scope.owner_user_id,
        ),
    ).task.model_dump()
    task_data.update(operation="query", policy=None)
    task_data["output"]["classification"] = "none"
    task_data["population"]["predicates"] = Predicate(
        reference=task_data["output"]["fields"][0]["reference"],
        operator="eq",
        values=(ScalarValue(data_type="TEXT", value="U1"),),
    ).model_dump()
    requested = SemanticTask.model_validate(task_data)
    compiler = QueryCompiler(context)
    with semantic_request(RequestIdentity(owner, None, 71, requested.question, "2026-10-29")):
        compiled = compiler.compile(prepare_task_plan(requested, compiler))
        from sqlglot import parse_one

        root = parse_one(compiled.validated.statement, read="postgres")
        if mutation == "where":
            root.set("where", None)
            altered = replace(
                compiled,
                validated=replace(compiled.validated, statement=root.sql(dialect="postgres")),
            )
        elif mutation == "limit":
            altered = replace(
                compiled,
                validated=replace(
                    compiled.validated, statement=root.limit(1).sql(dialect="postgres")
                ),
            )
        elif mutation == "parameters":
            altered = replace(compiled, parameters={key: "U2" for key in compiled.parameters})
        else:
            altered = replace(compiled, evidence_sql="SELECT 1")
        with pytest.raises(ModelResponseError):
            verify_compiled_task(requested, altered, compiler)


def test_output_order_by_an_ambiguous_metric_source_cannot_choose_an_alias_silently():
    from app.semantic.presentation import select_verified_rows
    from app.semantic.task import Ordering, OutputSelection, Projection
    from app.text_to_sql.answer import ResultColumn

    output = OutputSelection(
        fields=(
            Projection(reference="t0.c0", alias="total", aggregate="sum"),
            Projection(reference="t0.c0", alias="average", aggregate="avg"),
        ),
        classification="all",
        ordering=(Ordering(field="t0.c0", direction="desc"),),
    )
    columns = (
        ResultColumn(key="total", label="Total", data_type="NUMERIC"),
        ResultColumn(key="average", label="Average", data_type="NUMERIC"),
    )
    with pytest.raises(ModelResponseError):
        select_verified_rows(output, [{"total": "100", "average": "10"}], ["qualified"], columns)


def test_demo_catalog_retains_its_declared_four_table_compiler_contract():
    from app.semantic.coverage import prepare_task_plan, verify_compiled_task
    from app.text_to_sql.compiler import QueryCompiler
    from app.text_to_sql.query_plan import PlanDecision, PlanExpression, PlanField, QueryPlan
    from app.text_to_sql.schema_context import default_sql_context
    from tests.semantic_fixtures import proposal_from_plan
    from tests.test_query_compiler import field, source

    context = default_sql_context()
    compiler = QueryCompiler(context, default_schema=True)
    category = field(compiler, "categories", "category_code")
    plan = QueryPlan(
        source=source(compiler, "order_items"),
        relationships=list(compiler.references.relationships),
        expressions=[
            PlanExpression(
                operation="multiply",
                arguments=[
                    field(compiler, "order_items", "quantity"),
                    field(compiler, "order_items", "unit_price"),
                ],
            ),
            PlanExpression(operation="sum", arguments=["e0"]),
        ],
        fields=[
            PlanField(reference=category, alias="category"),
            PlanField(reference="e1", alias="revenue"),
        ],
        group_by=[category],
    )
    requested = proposal_from_plan(PlanDecision(plan=plan)).task("Revenue per category")
    with semantic_request(
        RequestIdentity(
            UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642"),
            None,
            None,
            requested.question,
            "2026-10-29",
        )
    ):
        bound = prepare_task_plan(requested, compiler)
        compiled = compiler.compile(bound)
        verify_compiled_task(requested, compiled, compiler)
    assert compiled.validated.statement.count("JOIN") == 3


def test_dimension_measure_cannot_rebase_an_explicit_fact_relationship_tree():
    from app.core.diagnostics import diagnostic_request
    from app.core.errors import SqlUnsupportedError
    from app.text_to_sql.compiler import SchemaReferences

    chunk, context, _ = fixture()
    original = bind_policy_task(task(), [chunk], context).task
    context = replace(
        context,
        table_columns={
            **context.table_columns,
            "random_d": context.table_columns["random_d"] | {"budget"},
        },
        column_types={
            **context.column_types,
            "random_d": {**context.column_types["random_d"], "budget": "NUMERIC"},
        },
    )
    dimension_value = next(
        key
        for key, location in SchemaReferences.from_context(context).columns.items()
        if location == ("random_d", "budget")
    )
    # Reissue all catalog references after the schema addition; only the metric
    # location changes, while the explicit original fact -> dimension edge remains.
    before = SchemaReferences.from_context(fixture()[1])
    after = SchemaReferences.from_context(context)
    mapping = {
        key: next(ref for ref, target in after.columns.items() if target == location)
        for key, location in before.columns.items()
    }
    data = original.model_dump()
    data["population"]["group_by"] = [mapping[ref] for ref in original.population.group_by]
    for field in data["output"]["fields"]:
        field["reference"] = (
            dimension_value if field["aggregate"] == "sum" else mapping[field["reference"]]
        )
    with diagnostic_request() as trace, pytest.raises(SqlUnsupportedError) as error:
        bind_policy_task(SemanticTask.model_validate(data), [chunk], context)
    assert error.value.code == "join_graph"
    assert error.value.error_context.validation_branch == "missing_path"
    assert any(
        event["stage"] == "join_graph" and event["status"] == "failure" for event in trace.events
    )


@pytest.mark.parametrize("direction,expected", [("asc", (1,)), ("desc", (2,))])
def test_unbound_policy_metric_order_is_bound_before_selecting_the_verified_subset(
    direction, expected
):
    from app.semantic.task import Ordering
    from app.text_to_sql.compiler import SchemaReferences
    from app.text_to_sql.query_plan import PlanExpression

    chunk, context, _ = fixture()
    owner = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")
    context = replace(context, dataset_id=71, owner_user_id=owner, table_row_counts={"random_d": 3})
    chunk = replace(
        chunk, document_scope=replace(chunk.document_scope, dataset_id=71, owner_user_id=owner)
    )
    amount = next(
        ref
        for ref, column in SchemaReferences.from_context(context).columns.items()
        if column == ("random_f", "amount")
    )
    request = task("not_qualified").model_copy(
        update={
            "expressions": (PlanExpression(operation="sum", arguments=[amount]),),
            "output": task("not_qualified").output.model_copy(
                update={"ordering": (Ordering(field="e0", direction=direction),), "limit": 1}
            ),
        }
    )
    rows = [
        {"entity_id": "U1", "metric_value": "40.00"},
        {"entity_id": "U2", "metric_value": "0.00"},
        {"entity_id": "U3", "metric_value": "10.00"},
    ]
    sql, executor, gateway = pipeline(context, rows)
    executor.execute.side_effect = [
        [{"entity_count": 3}],
        [{"entity_id": row["entity_id"]} for row in rows],
        rows,
    ]
    with semantic_request(RequestIdentity(owner, None, 71, request.question, "2026-10-29")):
        result = HybridPipeline(
            sql, Mock(retrieve=Mock(return_value=[chunk])), gateway, context
        ).run(request.question, task=request)
    assert result.verification_status == "verified_classification"
    assert result.answer_row_indices == expected and result.rows == rows
    assert result.task.output.ordering[0].field == "metric_value"
    assert executor.execute.call_count == 3
    gateway.generate_structured.assert_not_called()


@pytest.mark.parametrize("mutation", ["aggregate", "column", "literal", "unknown"])
def test_unbound_policy_sort_cannot_substitute_an_unverified_metric(mutation):
    from app.semantic.task import Ordering
    from app.text_to_sql.compiler import SchemaReferences
    from app.text_to_sql.query_plan import PlanExpression

    chunk, context, _ = fixture()
    refs = SchemaReferences.from_context(context)
    amount = next(ref for ref, column in refs.columns.items() if column == ("random_f", "amount"))
    node = PlanExpression(operation="sum", arguments=[amount])
    if mutation == "aggregate":
        node = PlanExpression(operation="avg", arguments=[amount])
    elif mutation == "column":
        node = PlanExpression(
            operation="sum", arguments=[next(ref for ref in refs.columns if ref != amount)]
        )
    elif mutation == "literal":
        node = PlanExpression(operation="literal", value="40", value_type="NUMERIC")
    request = task().model_copy(
        update={
            "expressions": (node,),
            "output": task().output.model_copy(
                update={
                    "ordering": (
                        Ordering(field="e99" if mutation == "unknown" else "e0", direction="asc"),
                    )
                }
            ),
        }
    )
    with pytest.raises(ModelResponseError) as error:
        bind_policy_task(request, [chunk], context)
    assert error.value.error_context.reason_code == "policy_metric_unbound"
