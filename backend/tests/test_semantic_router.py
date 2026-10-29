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
        {"operation": "sum", "arguments": ["t0.c0"], "value": "", "value_type": "none"},
        {"operation": "literal", "arguments": [], "value": "0.00", "value_type": "NUMERIC"},
        {"operation": "gt", "arguments": ["t0.c0", "e1"], "value": "", "value_type": "none"},
        {"operation": "is_null", "arguments": ["t0.c0"], "value": "", "value_type": "none"},
        {"operation": "or", "arguments": ["e2", "e3"], "value": "", "value_type": "none"},
        {
            "operation": "literal",
            "arguments": [],
            "value": "9007199254740993.0001",
            "value_type": "NUMERIC",
        },
        {"operation": "gte", "arguments": ["e0", "e5"], "value": "", "value_type": "none"},
    ]
    data.update(
        where="e4",
        having="e6",
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
