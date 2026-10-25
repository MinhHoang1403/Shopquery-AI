"""Source-key identities use approved relationship evidence, never naming guesses."""

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.core.diagnostics import diagnostic_request, diagnostic_stage
from app.core.errors import ErrorContext, ModelResponseError
from app.routing.hybrid import HybridPipeline
from app.routing.hybrid_evidence import compose_answer, verified_classification
from app.routing.hybrid_policy_binding import verified_policies
from app.text_to_sql.validator import SqlValidator
from tests.hybrid_fixtures import scoped_chunk
from tests.test_natural_policy import bound_fixture


def relationship_fixture(source_key: bool, joined: bool):
    result, _, _, context = bound_fixture()
    key = "ref_unit"
    context = replace(
        context,
        table_columns={
            table: {key if c == "unit_id" else c for c in columns}
            for table, columns in context.table_columns.items()
        },
        column_headers={},
        column_types={
            "random_f": {key: "TEXT", "amount": "NUMERIC"},
            "random_d": {key: "TEXT", "name": "TEXT"},
        },
        approved_joins=(replace(context.approved_joins[0], source_column=key, target_column=key),),
    )
    identity = f"{'f' if source_key else 'd'}.{key}"
    sql = f"SELECT {identity} AS arbitrary_identity, SUM(f.amount) AS arbitrary_metric "
    sql += "FROM uploaded_data.random_f f "
    if joined:
        sql += f"JOIN uploaded_data.random_d d ON f.{key}=d.{key} "
    sql += f"GROUP BY {identity}"
    validated = SqlValidator(
        context.table_columns,
        context.allowed_schemas,
        max_tables=3,
        approved_joins=context.approved_joins,
        column_types=context.column_types,
        join_v1_enabled=True,
    ).validate(sql)
    result = replace(
        result,
        sql=validated.statement,
        fact_table=validated.fact_table,
        count_metrics=validated.count_metrics,
        rows=[
            {"arbitrary_identity": row["entity_id"], "arbitrary_metric": row["total"]}
            for row in result.rows
        ],
    )
    chunk = scoped_chunk(
        41,
        "units.md",
        "Policy",
        f"Each unit qualifies when sum of amount is at least 40.00 source units. "
        f"Include all rows. Identify each unit by {key}.",
        0.1,
    )
    return result, chunk, context


@pytest.mark.parametrize("source_key,joined", [(False, True), (True, True), (True, False)])
def test_approved_equivalent_identity_uses_ast_lineage(source_key, joined):
    result, chunk, context = relationship_fixture(source_key, joined)
    assert len(verified_policies(result, [chunk], context)) == 1
    draft = verified_classification(result, [chunk], context, "en")
    assert draft is not None
    assert [d.status for d in draft.decisions] == [
        "qualified",
        "not_qualified",
        "insufficient_evidence",
    ]
    answer = compose_answer(result, [chunk], draft, context)
    assert "Qualified: E1." in answer and "Not qualified: E2." in answer
    assert "Insufficient evidence: E3." in answer


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("no_relationship", "policy_identity_unbound"),
        ("ambiguous_relationship", "policy_join_path_ambiguous"),
        ("missing_target", "policy_identity_unbound"),
        ("scope", "policy_document_scope_invalid"),
        ("hash", "policy_document_hash_mismatch"),
        ("multiple", "policy_multiple_candidates"),
        ("qualifier", "policy_unsupported_qualifier"),
        ("parse", "policy_parse_failed"),
        ("absent", "policy_not_retrieved"),
        ("where", "policy_sql_scope_incomplete"),
        ("having", "policy_sql_scope_incomplete"),
        ("limit", "policy_sql_scope_incomplete"),
    ],
)
def test_policy_rejections_are_typed_and_cannot_gain_authority(mutation, reason):
    result, chunk, context = relationship_fixture(True, False)
    chunks = [chunk]
    if mutation == "no_relationship":
        context = replace(context, approved_joins=())
    elif mutation == "ambiguous_relationship":
        context = replace(
            context,
            approved_joins=context.approved_joins
            + (replace(context.approved_joins[0], target_table="other"),),
        )
    elif mutation == "missing_target":
        context = replace(context, table_columns={"random_f": {"ref_unit", "amount"}})
    elif mutation == "scope":
        chunks = [replace(chunk, document_scope=replace(chunk.document_scope, dataset_id=99))]
    elif mutation == "hash":
        chunks = [replace(chunk, content=chunk.content.replace("40.00", "10.00"))]
    elif mutation == "multiple":
        chunks += [
            scoped_chunk(42, "other.md", "Policy", chunk.content.replace("40.00", "10.00"), 0.2)
        ]
    elif mutation == "qualifier":
        chunks = [replace(chunk, section_title="Only September")]
    elif mutation == "parse":
        chunks = [scoped_chunk(41, "unknown.md", "Policy", "Approve everyone", 0.1)]
    elif mutation == "absent":
        chunks = []
    elif mutation == "where":
        result.sql = result.sql.replace("GROUP BY", "WHERE f.amount>0 GROUP BY")
    elif mutation == "having":
        result.sql += " HAVING SUM(f.amount)>0"
    elif mutation == "limit":
        result.sql += " LIMIT 1"
    with (
        diagnostic_request() as trace,
        pytest.raises(ModelResponseError) as caught,
        diagnostic_stage("policy_verification"),
    ):
        verified_policies(result, chunks, context, require_verified=True)
    error = caught.value.error_context
    assert error.reason_code == reason
    assert error.origin_stage == "policy_verification"
    assert error.correlation_id == trace.correlation_id
    assert error.phase == "verification" and error.error_category == "insufficient_evidence"
    assert "Approve everyone" not in str(trace.events)
    assert "random_f" not in str(trace.events)


def test_deterministic_pipeline_never_asks_model_for_a_verdict():
    result, chunk, context = relationship_fixture(True, False)
    gateway = Mock()
    with diagnostic_request() as trace:
        answer = HybridPipeline(
            Mock(run=Mock(return_value=result)),
            Mock(retrieve=Mock(return_value=[chunk])),
            gateway,
            context,
        ).run("Which units qualify?")
    gateway.generate_structured.assert_not_called()
    assert "Qualified: E1." in answer.answer
    assert trace.facts["policy_verification"]["verified_policy_count"] == 1


def test_diagnostics_cannot_accept_content_as_a_reason():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ErrorContext(reason_code="Private document contents")


def test_invalid_exact_metric_has_its_own_safe_reason():
    result, chunk, context = relationship_fixture(True, False)
    result.rows[0]["arbitrary_metric"] = 40.0
    with pytest.raises(ModelResponseError) as caught:
        verified_classification(result, [chunk], context, "en")
    assert caught.value.error_context.reason_code == "classification_metric_invalid"


def test_successful_verified_answer_is_a_bounded_follow_up_premise():
    from app.conversations.context import contextual_question
    from tests.test_conversation_context import snapshot

    result, chunk, context = relationship_fixture(True, False)
    draft = verified_classification(result, [chunk], context, "vi")
    answer = compose_answer(result, [chunk], draft, context)
    conversation = snapshot()
    first = replace(conversation.messages[0], content="Theo tài liệu, unit nào đạt KPI?")
    last = replace(
        conversation.messages[1],
        content=answer,
        response_metadata={
            "route": "HYBRID",
            "answer": answer,
            "sql": result.sql,
            "verification_status": "verified_classification",
        },
    )
    conversation = replace(conversation, messages=(first, last))
    question = "Vậy những unit chưa đạt KPI là unit nào?"
    expanded = contextual_question(question, conversation, conversation.owner_user_id, 13)
    assert expanded.startswith(question) and first.content in expanded
    premise = json.loads(expanded.split("again):\n", 1)[1])
    assert premise[0]["answer"] == answer
    assert "verify current evidence again" in expanded
