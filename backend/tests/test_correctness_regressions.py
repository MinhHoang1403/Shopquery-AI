"""Structural reproductions of post-handoff failures, without private plans or data."""

from dataclasses import replace
from unittest.mock import Mock
from uuid import UUID

import pytest

from app.core.errors import ModelResponseError
from app.routing.hybrid import HybridPipeline
from app.routing.hybrid_evidence import compose_answer
from app.routing.router import RouteDecision, RouteLabel
from app.routing.service import DatasetChatService
from app.semantic.request import RequestIdentity, semantic_request
from app.text_to_sql.generation_contract import GenerationDecision
from app.text_to_sql.plan_binding import bind_approved_grain
from app.text_to_sql.query_plan import PlanExpression, PlanField, QueryPlan
from tests.semantic_fixtures import proposal_for_evidence
from tests.test_evidence_coverage import fixture as coverage_fixture
from tests.test_evidence_coverage import pipeline
from tests.test_hybrid_answer_consistency import fixture
from tests.test_plan_binding import setup_plan
from tests.test_query_compiler import field, source


@pytest.mark.parametrize("grouping", ["entity", "category"])
def test_scalar_fact_aggregates_have_no_dimension_grouping_grain(grouping):
    _, compiler, _ = setup_plan()
    plan = QueryPlan(
        source=source(compiler, "payments"),
        expressions=[
            PlanExpression(operation="row_count"),
            PlanExpression(operation="sum", arguments=[field(compiler, "payments", "amount")]),
        ],
        fields=[PlanField(reference="e0", alias="n"), PlanField(reference="e1", alias="total")],
        relationships=list(compiler.references.relationships),
        grouping=grouping,
    )
    compiled = compiler.compile(bind_approved_grain(plan, compiler.references))
    assert "GROUP BY" not in compiled.evidence_sql
    assert "COUNT(*)" in compiled.evidence_sql and "SUM(" in compiled.evidence_sql.upper()
    assert compiled.validated.count_metrics[0].root_fact == "payments"


def test_provider_schema_requires_a_real_literal_type_in_its_literal_branch():
    schema = GenerationDecision.model_json_schema()
    expression = schema["$defs"]["GenerationExpression"]
    assert "anyOf" in expression
    literal = next(
        b for b in expression["anyOf"] if b["properties"]["operation"].get("enum") == ["literal"]
    )
    assert "none" not in literal["properties"]["value_type"]["enum"]
    assert "DATE" in literal["properties"]["value_type"]["enum"]


@pytest.mark.parametrize("constant", ["'2032-04-09'", "42", "NULL"])
def test_unverified_classification_cannot_present_a_constant_as_its_metric(constant):
    result, chunks, draft = fixture()
    result.sql = result.sql.replace("SUM(f.measure)", constant)
    result.rows = [{**r, "total": "2032-04-09"} for r in result.rows]
    chunks = [replace(chunks[0], content="Policy explanation without an executable rule.")]
    draft = draft.model_copy(
        update={
            "rule_id": None,
            "decisions": [d.model_copy(update={"status": "unverified"}) for d in draft.decisions],
        }
    )
    with pytest.raises(ModelResponseError):
        compose_answer(result, chunks, draft)


def test_unverified_classification_preserves_real_aggregate_evidence_without_verdicts():
    result, chunks, draft = fixture()
    chunks = [replace(chunks[0], content="Policy explanation without an executable rule.")]
    draft = draft.model_copy(
        update={
            "rule_id": None,
            "decisions": [d.model_copy(update={"status": "unverified"}) for d in draft.decisions],
        }
    )
    answer = compose_answer(result, chunks, draft)
    assert "Unverified" in answer
    assert "Qualified:" not in answer and "Not qualified:" not in answer


@pytest.mark.parametrize("selection", ["all", "qualified", "not_qualified"])
def test_typed_classification_intent_uses_bound_evidence_without_a_question_template(selection):
    chunk, context, _ = coverage_fixture()
    owner = UUID("f425b6ce-7ff0-4329-9948-4e9bf2e93642")
    context = replace(context, dataset_id=71, owner_user_id=owner, table_row_counts={"random_d": 2})
    chunk = replace(
        chunk, document_scope=replace(chunk.document_scope, dataset_id=71, owner_user_id=owner)
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
    rag = Mock(retrieve=Mock(return_value=[chunk]))
    hybrid = HybridPipeline(sql, rag, gateway, context)
    router = Mock(
        route=Mock(
            return_value=RouteDecision(
                task=proposal_for_evidence("both", selection).task(
                    "Đánh giá chính sách cho toàn bộ đối tượng."
                ),
                evidence_requirement="both",
                route=RouteLabel.HYBRID,
                reason="typed fixture",
                policy_intent=selection,
                policy_scope="all_entities",
            )
        )
    )
    with semantic_request(
        RequestIdentity(owner, None, 71, "Đánh giá chính sách cho toàn bộ đối tượng.", "2026-10-29")
    ):
        result = DatasetChatService(router, sql, rag, hybrid).chat(
            "Đánh giá chính sách cho toàn bộ đối tượng."
        )
    assert result.verification_status == "verified_classification"
    assert len(result.rows) == 2
    assert (
        result.answer_row_indices
        == {"all": None, "qualified": (0,), "not_qualified": (1,)}[selection]
    )
    assert executor.execute.call_count == 3
    gateway.generate_structured.assert_not_called()


def test_unknown_policy_stops_typed_classification_before_sql_or_model_drafting():
    chunk, context, _ = coverage_fixture()
    chunk = replace(chunk, content="An incomplete document with unverified conditions.")
    sql, gateway = Mock(), Mock()
    with pytest.raises(ModelResponseError) as caught:
        HybridPipeline(sql, Mock(retrieve=Mock(return_value=[chunk])), gateway, context).run(
            "Classify all entities", classification="all"
        )
    assert caught.value.error_context.reason_code == "policy_parse_failed"
    sql.run.assert_not_called()
    gateway.generate_structured.assert_not_called()


def test_filtered_intent_never_substitutes_a_full_workspace_plan():
    hybrid = Mock()
    router = Mock(
        route=Mock(
            return_value=RouteDecision(
                evidence_requirement="both",
                route=RouteLabel.HYBRID,
                reason="explicit subset",
                policy_intent="qualified",
                policy_scope="filtered_entities",
            )
        )
    )
    # A legacy scope flag without its semantic task is a contract error, not authority.
    with pytest.raises(ModelResponseError):
        DatasetChatService(router, Mock(), Mock(), hybrid).chat(
            "Only entities in an explicit subset"
        )
    hybrid.run.assert_not_called()


def test_date_literal_retains_its_type_and_cannot_obtain_numeric_provenance_from_its_alias():
    _, compiler, _ = setup_plan()
    plan = QueryPlan(
        source=source(compiler, "payments"),
        expressions=[PlanExpression(operation="literal", value="2032-04-09", value_type="DATE")],
        fields=[PlanField(reference="e0", alias="total_money")],
    )
    column = compiler.compile(plan).result_columns[0]
    assert column.data_type == "DATE" and column.provenance == "literal"
    assert not column.numeric and column.aggregate is None
