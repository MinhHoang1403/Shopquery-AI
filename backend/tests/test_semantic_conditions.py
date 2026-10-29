"""Compact condition/projection transport; no provider or production database."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.datasets.context import DatasetSqlContext
from app.routing.router import QueryRouter
from app.semantic import wire
from app.semantic.planning import task_query_plan
from app.semantic.wire import TaskProposal
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.count_contract import CountKind
from tests.semantic_fixtures import proposal
from tests.test_semantic_router import gateway


@pytest.mark.parametrize("provider", ["inetcloud-knowledge", "gemini"])
def test_captured_provider_filter_preserves_source_operator_and_literal(provider):
    captures = json.loads(
        Path(__file__)
        .with_name("fixtures")
        .joinpath("semantic_provider_proposals.json")
        .read_text(encoding="utf-8")
    )["records"]
    captured = next(c for c in captures if c["provider"] == provider and c["case"] == "p14")
    task = TaskProposal.model_validate(captured["proposal"]).task(
        captured["question"],
        column_references={"column:t0.name": "t0.c1", "column:t0.room_count": "t0.c3"},
    )
    assert [p.reference for p in task.output.fields] == ["t0.c1", "t0.c3"]
    predicate = task.population.predicates
    assert (predicate.reference, predicate.operator) == ("t0.c3", "gt")
    assert [(v.data_type, v.value) for v in predicate.values] == [("BIGINT", "120")]
    assert task.output.classification == "none" and task.output.limit is None


def test_captured_district_failure_stays_a_mismatch_without_verified_mapping():
    captures = json.loads(
        Path(__file__)
        .with_name("fixtures")
        .joinpath("semantic_provider_proposals.json")
        .read_text(encoding="utf-8")
    )["records"]
    captured = next(c for c in captures if c["case"] == "p17")
    task = TaskProposal.model_validate(captured["proposal"]).task(
        captured["question"], column_references={"column:t0.district": "t0.c1"}
    )
    # This test records the failure; conversion success must never count as entailment.
    assert task.population.predicates.values[0].value == "3"
    assert task.population.predicates.values[0].value != "quận 3"


def comparison(left="t0.c0", operator="gt", values=None, value_type="NUMERIC"):
    return {
        "kind": "comparison",
        "left": left,
        "operator": operator,
        "values": ["0.00"] if values is None else values,
        "value_type": value_type,
        "children": [],
    }


def group(children, kind="all"):
    return {
        "kind": kind,
        "left": "",
        "operator": "none",
        "values": [],
        "value_type": "none",
        "children": children,
    }


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_actual_sdk_simple_measures_need_no_literal_or_boolean_expression_nodes(
    monkeypatch, provider
):
    context = DatasetSqlContext(
        "Synthetic",
        {"events": {"amount"}},
        {"events": "uploaded_data"},
        column_types={"events": {"amount": "NUMERIC"}},
    )
    data = proposal()
    data.update(
        expressions=[],
        fields=[
            {"reference": "", "alias": "rows", "aggregation": "row_count"},
            {"reference": "column:t0.amount", "alias": "total", "aggregation": "sum"},
            {"reference": "column:t0.amount", "alias": "values", "aggregation": "non_null_count"},
        ],
        conditions=[comparison("column:t0.amount")],
        where="p0",
    )
    selected, calls = gateway(monkeypatch, provider, data)
    try:
        task = (
            QueryRouter(selected, context=context)
            .route("Count records and sum the selected values.")
            .task
        )
        assert not task.expressions and task.population.predicates.values[0].value == "0.00"
        compiled = QueryCompiler(context).compile(task_query_plan(task))
        assert [count.kind for count in compiled.validated.count_metrics] == [
            CountKind.ROW_COUNT,
            CountKind.NON_NULL_VALUE_COUNT,
        ]
        assert len(calls) == 1
    finally:
        selected.close()


@pytest.mark.parametrize(
    "mutation",
    [
        "orphan",
        "forward",
        "cycle",
        "mixed_group",
        "leaf_children",
        "missing_type",
        "wrong_null_arity",
        "boolean_value",
        "unused_value",
    ],
)
def test_invalid_conditions_never_drop_or_reinterpret_a_requirement(mutation):
    data = proposal()
    data.update(conditions=[comparison()], where="p0")
    if mutation == "orphan":
        data["where"] = ""
    elif mutation in {"forward", "cycle"}:
        data["conditions"] = [group(["p1" if mutation == "forward" else "p0"])]
    elif mutation == "mixed_group":
        data["conditions"] = [comparison(), {**group(["p0"]), "left": "t0.c0"}]
        data["where"] = "p1"
    elif mutation == "leaf_children":
        data["conditions"][0]["children"] = ["p0"]
    elif mutation == "missing_type":
        data["conditions"][0]["value_type"] = "none"
    elif mutation == "wrong_null_arity":
        data["conditions"][0]["operator"] = "is_null"
    elif mutation == "boolean_value":
        data["expressions"] = [
            {"operation": "eq", "arguments": ["t0.c0"], "value": "", "value_type": "none"}
        ]
    else:
        data["expressions"].append(
            {"operation": "literal", "arguments": [], "value": "2", "value_type": "NUMERIC"}
        )
    with pytest.raises(ValueError):
        TaskProposal.model_validate(data).task("Synthetic conditions.")


def test_expansion_is_bounded_before_constructing_a_shared_boolean_tree(monkeypatch):
    data = proposal()
    data.update(
        conditions=[comparison(), group(["p0"] * 20), group(["p1"] * 20), group(["p2"] * 20)],
        where="p3",
    )
    actual_predicate, constructed = wire.Predicate, 0

    def bounded(**kwargs):
        nonlocal constructed
        constructed += 1
        if constructed > 100:
            pytest.fail("Condition expanded before its resource guard")
        return actual_predicate(**kwargs)

    monkeypatch.setattr(wire, "Predicate", bounded)
    with pytest.raises(ValueError, match="bounded"):
        TaskProposal.model_validate(data).task("Synthetic group expansion.")
    assert constructed <= 80


def test_date_interval_and_or_null_preserve_typed_values_and_topology():
    data = proposal()
    data.update(
        conditions=[
            comparison("t0.c1", "gte", ["2032-09-01T00:00:00+07:00"], "TIMESTAMPTZ"),
            comparison("t0.c1", "lt", ["2032-10-01T00:00:00+07:00"], "TIMESTAMPTZ"),
            group(["p0", "p1"]),
            comparison("t0.c1", "is_null", [], "none"),
            group(["p2", "p3"], "any"),
        ],
        where="p4",
    )
    task = TaskProposal.model_validate(deepcopy(data)).task("Selected interval or missing date.")
    predicate = task.population.predicates
    assert predicate.kind == "any" and predicate.children[0].kind == "all"
    assert predicate.children[0].children[0].values[0].value == "2032-09-01T00:00:00+07:00"
    assert predicate.children[0].children[1].operator == "lt"
    assert predicate.children[1].operator == "is_null" and predicate.children[1].values == ()


@pytest.mark.parametrize("reference", ["e-1", "e+0", "e00"])
def test_unissued_expression_spellings_cannot_alias_a_valid_array_index(reference):
    data = proposal()
    data["fields"][0]["reference"] = reference
    with pytest.raises(ValueError):
        TaskProposal.model_validate(data).task("Synthetic unissued reference.")


def test_projection_wire_uses_the_same_alias_contract_as_the_domain():
    data = proposal()
    data["fields"][0]["alias"] = "not-an-internal-alias"
    with pytest.raises(ValueError):
        TaskProposal.model_validate(data)
