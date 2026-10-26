import json

import pytest
from pydantic import ValidationError

from app.core.errors import ModelResponseError
from app.text_to_sql.generation_contract import GenerationDecision
from app.text_to_sql.query_plan import PlanDecision
from tests.test_plan_providers import gateway_harness, response
from tests.test_planning_outcomes import wire


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize("kind", ["forward", "depth", "expansion"])
def test_domain_dag_bounds_have_exact_safe_branches(monkeypatch, provider, kind):
    nodes = [{"operation": "literal", "arguments": [], "value": "1", "value_type": "BIGINT"}]
    if kind == "forward":
        nodes = [{"operation": "sum", "arguments": ["e1"], "value": "", "value_type": "none"}]
    elif kind == "depth":
        nodes += [
            {"operation": "add", "arguments": [f"e{i}", "t0.c0"], "value": "", "value_type": "none"}
            for i in range(8)
        ]
    else:
        nodes += [
            {"operation": "add", "arguments": [f"e{i}"] * 100, "value": "", "value_type": "none"}
            for i in range(2)
        ]
    gateway, calls = gateway_harness(
        monkeypatch, provider, [response(provider, json.dumps(wire(expressions=nodes)))]
    )
    try:
        with pytest.raises(ModelResponseError) as caught:
            gateway.generate_structured("Q", PlanDecision)
        assert (
            caught.value.error_context.validation_branch
            == {
                "forward": "expression_forward_reference",
                "depth": "expression_depth",
                "expansion": "expression_expansion",
            }[kind]
        )
        assert len(calls) == 1
    finally:
        gateway.close()


@pytest.mark.parametrize(
    "updates",
    [
        {"source": None},
        {"fields": [{"reference": "t0.c0", "alias": ""}]},
        {"filters": [{"reference": "t0.c0", "operator": "DROP"}]},
    ],
)
def test_invalid_wire_fields_fail_before_conversion(updates):
    with pytest.raises(ValidationError):
        GenerationDecision.model_validate(wire(**updates))


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
@pytest.mark.parametrize(
    "node,branch,location",
    [
        (
            {"operation": "literal", "arguments": [], "value": "100", "value_type": "none"},
            "literal_type_missing",
            ["expressions", 0, "value_type"],
        ),
        (
            {
                "operation": "row_count",
                "arguments": [],
                "value": "private-data",
                "value_type": "none",
            },
            "nonliteral_value",
            ["expressions", 0, "value"],
        ),
        (
            {"operation": "row_count", "arguments": [], "value": "", "value_type": "BIGINT"},
            "nonliteral_type",
            ["expressions", 0, "value_type"],
        ),
    ],
)
def test_conversion_rejection_preserves_exact_safe_branch(
    monkeypatch, provider, node, branch, location
):
    payload = wire(expressions=[node])
    GenerationDecision.model_validate(payload)  # Wire shape is valid, domain meaning is not.
    gateway, calls = gateway_harness(
        monkeypatch, provider, [response(provider, json.dumps(payload))]
    )
    try:
        with pytest.raises(ModelResponseError) as caught:
            gateway.generate_structured("Q", PlanDecision)
        context = caught.value.error_context
        assert context.phase == "domain_conversion"
        assert context.validation_branch == branch
        assert context.validation_location == location
        assert context.response_outcome == "query"
        assert "private-data" not in context.model_dump_json()
        assert len(calls) == 1
    finally:
        gateway.close()


def test_valid_numeric_filter_and_sentinel_conversion():
    decision = GenerationDecision.model_validate(
        wire(
            fields=[{"reference": "t0.c0", "alias": "hotel"}],
            expressions=[
                {"operation": "literal", "arguments": [], "value": "100", "value_type": "BIGINT"}
            ],
            filters=[{"reference": "t0.c1", "operator": "gt", "values": ["100"]}],
            sort=[{"field": "hotel", "direction": "asc", "nulls": "last"}],
        )
    ).decision()
    assert decision.plan.relationships == []
    assert decision.plan.filters[0].operator == "gt"
    assert (
        decision.plan.limit is None and decision.plan.where is None and decision.plan.having is None
    )
    assert decision.plan.expressions[0].value_type == "BIGINT"


@pytest.mark.parametrize("provider", ["knowledge", "gemini"])
def test_nested_domain_validation_is_distinguished_from_expression_conversion(
    monkeypatch, provider
):
    payload = wire(fields=[])
    gateway, calls = gateway_harness(
        monkeypatch, provider, [response(provider, json.dumps(payload))]
    )
    try:
        with pytest.raises(ModelResponseError) as caught:
            gateway.generate_structured("Q", PlanDecision)
        context = caught.value.error_context
        assert context.validation_branch == "query_plan_contract"
        assert context.validation_location == ["fields"]
        assert context.validation_type == "too_short"
        assert len(calls) == 1
    finally:
        gateway.close()
