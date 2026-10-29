"""Actual SDK transports and a single semantic proposal; no paid requests."""

import json
from unittest.mock import Mock

import pytest

from app.core.errors import ModelResponseError
from app.routing.router import QueryRouter, RouteLabel
from app.semantic.planning import task_query_plan
from app.semantic.wire import TaskProposal
from tests.semantic_fixtures import proposal
from tests.test_gemini import _build_harness
from tests.test_plan_providers import response
from tests.test_providers import harness


def gateway(monkeypatch, provider, payload):
    replies = [response(provider, json.dumps(payload))]
    if provider == "knowledge":
        return harness(
            monkeypatch, replies, inetcloud_retry_attempts=1, ai_gemini_fallback_enabled=False
        )
    run = _build_harness(monkeypatch, replies, attempts=1)
    return run.gateway, run.calls


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_one_actual_sdk_proposal_produces_same_domain_task(monkeypatch, provider):
    selected, calls = gateway(monkeypatch, provider, proposal())
    try:
        decision = QueryRouter(selected).route("Đếm số dòng hiện có.")
        assert decision.route == RouteLabel.SQL and decision.task.question == "Đếm số dòng hiện có."
        assert task_query_plan(decision.task).expressions[0].operation == "row_count"
        assert len(calls) == 1
        body = json.loads(calls[0].content)
        schema = (
            body["response_format"]["json_schema"]["schema"]
            if provider == "knowledge"
            else body["generationConfig"]["responseSchema"]
        )
        assert "operation" in schema["properties"] and "route" not in schema["properties"]
        for forbidden in ("owner_user_id", "dataset_id", "verified", "threshold"):
            assert forbidden not in schema["properties"]
        if provider == "gemini":
            assert "anyOf" not in json.dumps(schema)
    finally:
        selected.close()


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize("mutation", ["missing", "extra", "type", "truncated", "old_flags"])
def test_invalid_proposal_never_mints_a_task_or_retries(monkeypatch, provider, mutation):
    data = proposal()
    if mutation == "missing":
        del data["selection"]
    elif mutation == "extra":
        data["verified"] = True
    elif mutation == "type":
        data["limit"] = "2"
    elif mutation == "old_flags":
        data = {"route": "HYBRID", "policy_intent": "qualified", "policy_scope": "all_entities"}
    if mutation == "truncated":
        replies = [response(provider, '{"operation":')]
        if provider == "knowledge":
            selected, calls = harness(monkeypatch, replies, inetcloud_retry_attempts=1)
        else:
            run = _build_harness(monkeypatch, replies, attempts=1)
            selected, calls = run.gateway, run.calls
    else:
        selected, calls = gateway(monkeypatch, provider, data)
    try:
        with pytest.raises(ModelResponseError):
            QueryRouter(selected).route("Câu hỏi tổng hợp.")
        assert len(calls) == 1
    finally:
        selected.close()


def test_explicit_route_still_checks_the_semantic_proposal():
    data = proposal("explain")
    data.update(source="", fields=[], expressions=[])
    service = Mock(generate_structured=Mock(return_value=TaskProposal.model_validate(data)))
    result = QueryRouter(service).route("/sql Quy định là gì?")
    assert result.route == RouteLabel.UNSUPPORTED
    service.generate_structured.assert_called_once()


def test_boolean_population_and_output_predicate_remain_distinct():
    data = proposal()
    data["fields"] = [{"reference": "e0", "alias": "total"}]
    data["expressions"] = [
        {"operation": "sum", "arguments": ["t0.c0"], "value": "", "value_type": "none"}
    ]
    data["conditions"] = [
        {
            "kind": "comparison",
            "left": "t0.c0",
            "operator": "gt",
            "values": ["0.00"],
            "value_type": "NUMERIC",
            "children": [],
        },
        {
            "kind": "comparison",
            "left": "t0.c0",
            "operator": "is_null",
            "values": [],
            "value_type": "none",
            "children": [],
        },
        {
            "kind": "any",
            "left": "",
            "operator": "none",
            "values": [],
            "value_type": "none",
            "children": ["p0", "p1"],
        },
        {
            "kind": "comparison",
            "left": "e0",
            "operator": "gte",
            "values": ["9007199254740993.0001"],
            "value_type": "NUMERIC",
            "children": [],
        },
    ]
    data.update(
        where="p2",
        having="p3",
        sort=[{"field": "total", "direction": "desc", "nulls": "last"}],
        limit=2,
    )
    task = TaskProposal.model_validate(data).task("Tổng theo các điều kiện đã nêu.")
    assert task.population.predicates.kind == "any"
    assert task.output.predicates.operator == "gte"
    plan = task_query_plan(task)
    assert plan.where != plan.having and plan.limit == 2
    assert any(e.value == "9007199254740993.0001" for e in plan.expressions)


def test_policy_can_wait_for_backend_metric_binding_without_losing_known_population():
    data = proposal("apply_policy")
    data.update(
        source="",
        fields=[],
        expressions=[],
        policy_description="Quy định workspace",
        selection="not_qualified",
    )
    task = TaskProposal.model_validate(data).task("Những đối tượng nào chưa đạt theo tài liệu?")
    assert task.policy.metric is None and task.population.source is None
    with pytest.raises(ValueError):
        task_query_plan(task)


def test_domain_conversion_preserves_safe_structural_diagnostics_without_response_text():
    data = proposal()
    data["sort"] = [{"field": "private_missing_alias", "direction": "asc", "nulls": "last"}]
    gateway = Mock(generate_structured=Mock(return_value=TaskProposal.model_validate(data)))
    with pytest.raises(ModelResponseError) as error:
        QueryRouter(gateway).route("PRIVATE_QUESTION")
    context = error.value.error_context.model_dump_json()
    assert error.value.error_context.validation_branch == "response_contract"
    assert error.value.error_context.validation_type == "value_error"
    assert "private_missing_alias" not in context and "PRIVATE_QUESTION" not in context
    gateway.generate_structured.assert_called_once()


def test_generation_column_addresses_are_named_and_lower_only_through_the_issued_catalog():
    from app.datasets.context import DatasetSqlContext

    context = DatasetSqlContext(
        "Synthetic catalog",
        {"sites": {"site_id", "name", "province", "room_count"}},
        {"sites": "uploaded_data"},
        column_types={
            "sites": {"site_id": "TEXT", "name": "TEXT", "province": "TEXT", "room_count": "BIGINT"}
        },
    )

    def respond(prompt, schema):
        catalog = json.JSONDecoder().raw_decode(prompt.split("Source/context data:\n")[1])[0][
            "catalog"
        ]
        rooms = next(
            column["id"] for column in catalog["columns"] if column["name"] == "room_count"
        )
        assert rooms == "column:t0.room_count"
        data = proposal()
        data.update(
            fields=[{"reference": rooms, "alias": "capacity"}],
            expressions=[],
            sort=[{"field": rooms, "direction": "desc", "nulls": "last"}],
        )
        assert "policy_selection" in schema.model_json_schema()["properties"]
        assert "selection" not in schema.model_json_schema()["properties"]
        return schema.model_validate(data)

    result = QueryRouter(
        Mock(generate_structured=Mock(side_effect=respond)), context=context
    ).route("List capacities.")
    assert result.task.output.fields[0].reference == "t0.c2"
    assert result.task.output.ordering[0].field == "t0.c2"


def test_named_column_from_another_catalog_cannot_be_guessed_or_repaired_from_its_alias():
    data = proposal()
    data.update(
        fields=[{"reference": "column:t99.room_count", "alias": "room_count"}], expressions=[]
    )
    selected = Mock(generate_structured=Mock(return_value=TaskProposal.model_validate(data)))
    with pytest.raises(ModelResponseError):
        QueryRouter(selected).route("List capacities.")
    selected.generate_structured.assert_called_once()


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_actual_sdk_named_column_and_predicate_lower_without_ordinal_guessing(
    monkeypatch, provider
):
    from app.datasets.context import DatasetSqlContext

    context = DatasetSqlContext(
        "Synthetic catalog",
        {"sites": {"name", "province", "room_count"}},
        {"sites": "uploaded_data"},
        column_types={"sites": {"name": "TEXT", "province": "TEXT", "room_count": "BIGINT"}},
    )
    data = proposal()
    data.update(
        fields=[
            {"reference": "column:t0.name", "alias": "name"},
            {"reference": "column:t0.room_count", "alias": "room_count"},
        ],
        expressions=[],
        conditions=[
            {
                "kind": "comparison",
                "left": "column:t0.room_count",
                "operator": "gt",
                "values": ["120"],
                "value_type": "BIGINT",
                "children": [],
            }
        ],
        where="p0",
    )
    selected, calls = gateway(monkeypatch, provider, data)
    try:
        task = (
            QueryRouter(selected, context=context)
            .route("List capacities above the threshold.")
            .task
        )
        assert [field.reference for field in task.output.fields] == ["t0.c0", "t0.c2"]
        assert task.population.predicates.reference == "t0.c2"
        assert task.population.predicates.operator == "gt"
        assert task.population.predicates.values[0].value == "120"
        body = json.loads(calls[0].content)
        schema = (
            body["response_format"]["json_schema"]["schema"]
            if provider == "knowledge"
            else body["generationConfig"]["responseSchema"]
        )
        if provider == "knowledge":
            assert "column:t0.room_count" in json.dumps(schema)
        # Gemini's existing compatibility serializer omits dynamic schema
        # enrichment. It still receives the exact named catalog, and backend
        # lowering verifies the scoped address after parsing the SDK response.
        assert "column:t0.room_count" in json.dumps(body)
        assert (
            "policy_selection" in schema["properties"] and "selection" not in schema["properties"]
        )
        assert len(calls) == 1
    finally:
        selected.close()


def test_ordinary_query_cannot_gain_a_policy_verdict_by_renaming_the_wire_field():
    data = proposal()
    data.pop("selection")
    data["policy_selection"] = "qualified"
    with pytest.raises(ValueError, match="Conflicting task"):
        TaskProposal.model_validate(data).task("Synthetic records meeting a numeric filter.")


def test_captured_query_policy_conflict_stays_rejected_without_repairing_its_column_alias():
    from pathlib import Path

    data = json.loads(
        Path(__file__)
        .with_name("fixtures")
        .joinpath("semantic_conversion_rejection.json")
        .read_text()
    )["proposal"]
    assert data["fields"][1] == {"reference": "t0.c2", "alias": "room_count"}
    with pytest.raises(ValueError):
        TaskProposal.model_validate(data).task("Synthetic filtered records.")


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_wire_non_null_count_preserves_nullable_count_provenance(monkeypatch, provider):
    from app.datasets.context import DatasetSqlContext
    from app.text_to_sql.compiler import QueryCompiler
    from app.text_to_sql.count_contract import CountKind, NonNullProof

    context = DatasetSqlContext(
        "Synthetic nullable values",
        {"events": {"amount"}},
        {"events": "uploaded_data"},
        column_types={"events": {"amount": "NUMERIC"}},
    )
    data = proposal()
    data.update(
        fields=[
            {"reference": "e0", "alias": "non_null_values"},
            {"reference": "e1", "alias": "rows"},
        ],
        expressions=[
            {
                "operation": "non_null_count",
                "arguments": ["column:t0.amount"],
                "value": "",
                "value_type": "none",
            },
            {"operation": "row_count", "arguments": [], "value": "", "value_type": "none"},
        ],
    )
    selected, calls = gateway(monkeypatch, provider, data)
    try:
        task = (
            QueryRouter(selected, context=context)
            .route("Count rows and separately non-null values.")
            .task
        )
        assert [node.operation for node in task.expressions] == ["value_count", "row_count"]
        compiled = QueryCompiler(context).compile(task_query_plan(task))
        assert [count.kind for count in compiled.validated.count_metrics] == [
            CountKind.NON_NULL_VALUE_COUNT,
            CountKind.ROW_COUNT,
        ]
        assert compiled.validated.count_metrics[0].non_null_proof == NonNullProof.UNKNOWN
        body = json.loads(calls[0].content)
        schema = (
            body["response_format"]["json_schema"]["schema"]
            if provider == "knowledge"
            else body["generationConfig"]["responseSchema"]
        )
        assert '"non_null_count"' in json.dumps(schema) and '"value_count"' not in json.dumps(
            schema
        )
        assert len(calls) == 1
    finally:
        selected.close()


def test_wire_non_null_count_cannot_claim_a_row_count_alias_without_proof():
    from app.core.errors import SqlUnsupportedError
    from app.datasets.context import DatasetSqlContext
    from app.text_to_sql.compiler import QueryCompiler

    context = DatasetSqlContext(
        "Synthetic nullable values",
        {"events": {"amount"}},
        {"events": "uploaded_data"},
        column_types={"events": {"amount": "NUMERIC"}},
    )
    data = proposal()
    data.update(
        fields=[{"reference": "e0", "alias": "fact_row_count"}],
        expressions=[
            {
                "operation": "non_null_count",
                "arguments": ["column:t0.amount"],
                "value": "",
                "value_type": "none",
            }
        ],
    )
    task = TaskProposal.model_validate(data).task(
        "Synthetic count", column_references={"column:t0.amount": "t0.c0"}
    )
    with pytest.raises(SqlUnsupportedError) as error:
        QueryCompiler(context).compile(task_query_plan(task))
    assert error.value.aggregate_reason == "count_wrong_argument_semantics"
