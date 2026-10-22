"""The supported COUNT contract is semantic, not a whitelist of display aliases."""

from unittest.mock import Mock

import pytest
from sqlglot import exp, parse_one

from app.core.errors import SqlUnsupportedError, SqlValidationError
from app.text_to_sql.count_contract import count_evidence
from app.text_to_sql.join_policy import ApprovedJoin
from tests.count_conformance import (
    POSITIVE_COUNTS,
    UNSAFE_COUNTS,
    output_names,
    selections,
    unsafe_query,
)
from tests.sql_validation_fixtures import ValidationPipeline
from tests.test_three_table_join import CHAIN_ORDERS, PC, PS, validator


@pytest.mark.parametrize("case", POSITIVE_COUNTS, ids=lambda c: c.name)
@pytest.mark.parametrize("topology", ["pair", "chain", "star"])
def test_supported_count_conformance(case, topology):
    bindings = CHAIN_ORDERS[0]
    relations = validator()._approved_joins
    if topology == "pair":
        bindings = bindings.split(" INNER JOIN uploaded_data.courses")[0]
        relations = (PS,)
    elif topology == "star":
        bindings = bindings.replace("s.course_id=c.course_id", "p.course_id=c.course_id")
        relations = (PS, PC)
    ordering = [
        s.format(key="student_id", measure="amount").replace("f.", "p.") for s in case.ordering
    ]
    ordering.append("s.student_id")
    sql = (
        "SELECT s.student_id,"
        + ",".join(selections(case, "student_id", "amount")).replace("f.", "p.")
        + f" {bindings} GROUP BY s.student_id ORDER BY "
        + ",".join(ordering)
        + " LIMIT 2"
    )
    checked = validator(relations)
    result = checked.validate(sql)
    assert [m.output_alias for m in result.count_metrics] == output_names(case, "amount")
    expected_kinds = [
        "non_null_value_count" if kind == "values" else "row_count"
        for _, _, kind in case.projections
    ]
    assert [m.kind.value for m in result.count_metrics] == expected_kinds
    assert all(m.root_fact == "payments" and m.relationships for m in result.count_metrics)
    assert checked.validate(result.statement) == result
    before, after = parse_one(sql, read="postgres"), parse_one(result.statement, read="postgres")
    assert before.args["group"] == after.args["group"]
    assert before.args["limit"] == after.args["limit"]
    assert len(list(before.find_all(exp.Count))) >= len(list(after.find_all(exp.Count)))


@pytest.mark.parametrize("case", UNSAFE_COUNTS, ids=lambda c: c.name)
def test_unsafe_count_conformance_never_reaches_guard_or_executor(case):
    base = (
        (
            "SELECT s.student_id AS entity_id,s.name AS entity_name,SUM(p.amount) AS total,"
            "AVG(p.amount) AS average,COUNT(*) AS rows,COUNT(p.amount) AS present "
            f"{CHAIN_ORDERS[0]} "
            "GROUP BY s.student_id,s.name"
        )
        .replace("p.", "f.")
        .replace("payments p", "payments f")
        .replace("s.", "d.")
        .replace("students s", "students d")
    )
    sql = unsafe_query(base, case, key="student_id", measure="amount", identifier="payment_id")
    executor, gateway, guard = Mock(), Mock(), Mock()
    pipeline = ValidationPipeline(
        Mock(generate=Mock(return_value=sql)), validator(), executor, gateway, guard
    )
    with pytest.raises(SqlValidationError) as caught:
        pipeline.run("Synthetic unsafe COUNT")
    if case.reason:
        assert isinstance(caught.value, SqlUnsupportedError)
        assert caught.value.aggregate_reason == case.reason
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()
    guard.assert_not_called()


@pytest.mark.parametrize("alias", ["x" * 64, '"' + "đ" * 32 + '"'])
def test_count_output_labels_cannot_be_silently_truncated_by_postgresql(alias):
    with pytest.raises(SqlUnsupportedError) as caught:
        validator().validate(f"SELECT COUNT(*) AS {alias} {CHAIN_ORDERS[0]}")
    assert caught.value.aggregate_reason == "count_projection_alias_ambiguous"


def test_count_metadata_uses_postgresql_utf8_identifier_case_not_python_lower():
    result = validator().validate(f"SELECT COUNT(*) AS Đếm {CHAIN_ORDERS[0]} ORDER BY COUNT(*)")
    assert result.count_metrics[0].output_alias == "Đếm"


def test_distinct_utf8_count_labels_resolve_their_own_projection():
    result = validator().validate(
        f"SELECT s.student_id,COUNT(*) AS Đếm,COUNT(p.amount) AS đếm {CHAIN_ORDERS[0]} "
        "GROUP BY s.student_id ORDER BY Đếm DESC,đếm ASC"
    )
    assert [m.output_alias for m in result.count_metrics] == ["Đếm", "đếm"]
    assert [m.kind.value for m in result.count_metrics] == ["row_count", "non_null_value_count"]


def test_count_group_reference_is_rejected_independent_of_ascii_case():
    with pytest.raises(SqlUnsupportedError) as caught:
        validator().validate(
            f"SELECT s.student_id,COUNT(*) AS EVENT_COUNT {CHAIN_ORDERS[0]} "
            "GROUP BY s.student_id,EVENT_COUNT"
        )
    assert caught.value.aggregate_reason == "count_group_reference"


@pytest.mark.parametrize(
    "alias", [f"business_metric_{n}" for n in range(12)] + ['"số_lần"', "PAYMENT_COUNT"]
)
def test_count_alias_metamorphism_preserves_kind_and_grounding_provenance(alias):
    sql = (
        f"SELECT s.student_id,COUNT(p.amount) AS {alias} {CHAIN_ORDERS[0]} "
        "WHERE p.amount>=0 GROUP BY s.student_id ORDER BY COUNT(p.amount) DESC LIMIT 2"
    )
    result = validator().validate(sql)
    evidence = count_evidence(result.count_metrics)
    assert evidence[0]["kind"] == "non_null_value_count"
    assert evidence[0]["nonnull_proof"] == "nullable_or_unknown"
    assert result.count_metrics[0].fact_column == "amount"
    assert "COUNT(p.amount)" in result.statement and "COUNT(*)" not in result.statement


def test_grounding_uses_count_provenance_not_a_misleading_business_label():
    sql = f"SELECT COUNT(p.amount) AS total_orders {CHAIN_ORDERS[0]}"
    gateway, executor = Mock(), Mock()
    executor.execute.return_value = [{"total_orders": 0}]
    gateway.generate_text.return_value = "Insufficient row-count evidence"
    result = ValidationPipeline(
        Mock(generate=Mock(return_value=sql)), validator(), executor, gateway
    ).run("How many rows?")
    prompt = gateway.generate_text.call_args.args[0]
    assert '"field": "total_orders", "kind": "non_null_value_count"' in prompt
    assert "state insufficient" in prompt
    assert result.answer == "Insufficient row-count evidence"


@pytest.mark.parametrize(
    "relationships",
    [
        (),
        (PS,),
        (PS, ApprovedJoin("second-fact", "courses", "course_id", "students", "course_id", "r")),
    ],
)
def test_count_cannot_authorize_missing_edges_or_a_two_fact_fanout(relationships):
    executor, gateway = Mock(), Mock()
    pipeline = ValidationPipeline(
        Mock(generate=Mock(return_value=f"SELECT COUNT(*) AS business_count {CHAIN_ORDERS[0]}")),
        validator(relationships),
        executor,
        gateway,
    )
    with pytest.raises(SqlValidationError):
        pipeline.run("Synthetic unauthorized COUNT graph")
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()


def test_single_table_count_does_not_hide_unknown_star_output_collisions():
    from app.text_to_sql.validator import SqlValidator

    executor, gateway = Mock(), Mock()
    pipeline = ValidationPipeline(
        Mock(generate=Mock(return_value="SELECT *,COUNT(*) FROM uploaded_data.payments")),
        SqlValidator({"payments": {"count"}}, {"payments": "uploaded_data"}, max_tables=1),
        executor,
        gateway,
    )
    with pytest.raises(SqlUnsupportedError) as caught:
        pipeline.run("Synthetic ambiguous output")
    assert caught.value.aggregate_reason == "count_projection_alias_ambiguous"
    executor.execute.assert_not_called()
