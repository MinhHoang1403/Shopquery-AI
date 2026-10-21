"""Clause metadata must explain a refusal without collecting SQL or identifiers."""

import json
from unittest.mock import Mock

import pytest

from app.core.diagnostics import diagnostic_request, record_facts
from app.core.errors import SqlUnsupportedError, SqlValidationError
from app.routing.hybrid import HybridPipeline
from app.routing.router import QueryRouter, RouteDecision, RouteLabel
from app.routing.service import DatasetChatService
from app.text_to_sql.generator import SqlDraft, SqlGenerator
from app.text_to_sql.pipeline import TextToSqlPipeline
from tests.test_three_table_join import CHAIN_ORDERS, PC, PS, validator


@pytest.mark.parametrize(
    "projection,suffix,clause,parent,reason",
    [
        ("COUNT(*) AS private_alias", "", "select", "Alias", None),
        ("COUNT(*)", "", "select", "Alias", None),
        (
            "SUM(p.amount) AS total",
            " ORDER BY COUNT(*)",
            "order_by",
            "Ordered",
            "count_order_unprojected",
        ),
        (
            "SUM(p.amount) AS total",
            " HAVING COUNT(*)>0",
            "having",
            "GT",
            "count_having_unsupported",
        ),
        (
            "SUM(p.amount) AS total",
            " ORDER BY COUNT(*)+1",
            "order_by",
            "Add",
            "count_clause_unsupported",
        ),
        ("COUNT(*)+1 AS total", "", "select", "Add", "projection_expression"),
        ("COALESCE(COUNT(*),0) AS total", "", "select", "Coalesce", "projection_expression"),
        (
            "COUNT(p.amount) AS fact_row_count",
            "",
            "select",
            "Alias",
            "count_wrong_argument_semantics",
        ),
        (
            "COUNT(DISTINCT p.student_id) AS fact_value_count",
            "",
            "select",
            "Alias",
            "argument_expression",
        ),
        ("COUNT(s.student_id) AS fact_value_count", "", "select", "Alias", "dimension_column"),
        ("COUNT(*) FILTER(WHERE p.amount>0) AS fact_row_count", "", "select", "Filter", "filter"),
    ],
)
def test_aggregate_refusal_exposes_only_bounded_ast_metadata(
    projection: str, suffix: str, clause: str, parent: str, reason: str | None, caplog
) -> None:
    sql = (
        f"SELECT s.student_id,s.name,{projection} {CHAIN_ORDERS[0]} "
        "GROUP BY s.student_id,s.name" + suffix
    )
    with (
        caplog.at_level("INFO", logger="app.core.diagnostics"),
        diagnostic_request() as trace,
    ):
        if reason is None:
            assert validator().validate(sql).count_metrics[0].kind.value == "row_count"
        else:
            with pytest.raises(SqlUnsupportedError) as caught:
                validator().validate(sql)
            assert caught.value.aggregate_reason == reason
    event = next(
        e for e in trace.events if e["stage"] == ("join_aggregate" if reason else "join_graph")
    )
    assert event["aggregate_function"] == "count"
    assert event["aggregate_clause"] == clause
    assert event["aggregate_parent_type"] == parent
    assert event["count_argument_shape"] in {"star", "column", "expression"}
    assert not event["normalization_applied"]
    for private in ("private_alias", "student_id", "payments", "amount", "SELECT", sql):
        assert private not in caplog.text and private not in json.dumps(trace.events)


@pytest.mark.parametrize("selected", ["COUNT(*)", "COUNT(p.student_id)"])
@pytest.mark.parametrize("ordered", ["COUNT(*)", "COUNT(p.student_id)"])
@pytest.mark.parametrize("three", [False, True])
def test_verified_inner_key_and_star_count_order_have_identical_row_semantics(
    selected: str, ordered: str, three: bool
) -> None:
    bindings = (
        CHAIN_ORDERS[0] if three else CHAIN_ORDERS[0].split("INNER JOIN uploaded_data.courses")[0]
    )
    checked = validator() if three else validator((PS,), limit=2)
    with diagnostic_request() as trace:
        result = checked.validate(
            f"SELECT s.student_id,s.name,{selected} AS fact_row_count {bindings} "
            f"GROUP BY s.student_id,s.name ORDER BY {ordered} DESC NULLS LAST LIMIT 2"
        )
    assert "ORDER BY fact_row_count DESC" in result.statement
    event = next(e for e in trace.events if e["stage"] == "aggregate_normalization")
    assert event["aggregate_clause"] == "order_by" and event["aggregate_parent_type"] == "Ordered"
    assert event["matching_selected_aggregate"] and event["normalization_candidate"]
    assert event["normalization_applied"]
    assert checked.validate(result.statement) == result


def test_arbitrary_diagnostic_values_are_discarded() -> None:
    with diagnostic_request() as trace:
        record_facts(
            aggregate_clause="secret table",
            aggregate_parent_type="secret column",
            count_argument_shape="private",
            projection_alias_contract="secret alias",
        )
    assert "secret" not in json.dumps(trace.events) and "private" not in json.dumps(trace.events)


def test_normalization_events_and_log_stream_are_bounded(caplog) -> None:
    sql = (
        f"SELECT s.student_id,COUNT(*) AS fact_row_count {CHAIN_ORDERS[0]} "
        "GROUP BY s.student_id ORDER BY " + ",".join(["COUNT(*)"] * 80)
    )
    with caplog.at_level("INFO", logger="app.core.diagnostics"), diagnostic_request() as trace:
        validator().validate(sql)
    assert len(trace.events) == 64
    messages = [r for r in caplog.records if r.getMessage().startswith("pipeline_diagnostic ")]
    assert len(messages) == 64


@pytest.mark.parametrize(
    "count,alias",
    [
        ("COUNT(*)", "fact_row_count"),
        ("COUNT(p.student_id)", "fact_row_count"),
        ("COUNT(p.student_id)", "fact_value_count"),
        ("COUNT(p.amount)", "fact_value_count"),
    ],
)
def test_selected_alias_diagnostic_contract_matches_supported_counts(count, alias):
    with diagnostic_request() as trace:
        validator().validate(
            f"SELECT s.student_id,{count} AS {alias} {CHAIN_ORDERS[0]} GROUP BY s.student_id"
        )
    assert trace.events[-1]["projection_alias_contract"] == "valid"


def test_aggregate_telemetry_failure_cannot_change_validation(monkeypatch) -> None:
    def fail(**kwargs):
        raise RuntimeError("diagnostics unavailable")

    monkeypatch.setattr("app.text_to_sql.count_contract.record_facts", fail)
    with pytest.raises(SqlUnsupportedError) as caught:
        validator().validate(
            f"SELECT s.student_id,COUNT(p.amount) AS fact_row_count {CHAIN_ORDERS[0]} "
            "GROUP BY s.student_id"
        )
    assert caught.value.aggregate_reason == "count_wrong_argument_semantics"
    validator().validate(
        f"SELECT s.student_id,COUNT(*) AS fact_row_count {CHAIN_ORDERS[0]} "
        "GROUP BY s.student_id ORDER BY COUNT(*)"
    )


@pytest.mark.parametrize(
    "projection,ordering",
    [
        ("COUNT(*) AS fact_row_count", "COUNT(p.amount)"),
        ("COUNT(p.amount) AS fact_value_count", "COUNT(*)"),
        ("COUNT(p.payment_id) AS fact_row_count", "COUNT(*)"),
    ],
)
def test_count_equivalence_never_repairs_nullable_or_non_key_metrics(projection, ordering):
    with pytest.raises(SqlValidationError):
        validator().validate(
            f"SELECT s.student_id,{projection} {CHAIN_ORDERS[0]} "
            f"GROUP BY s.student_id ORDER BY {ordering}"
        )


@pytest.mark.parametrize("bindings", CHAIN_ORDERS)
def test_key_count_order_uses_metadata_root_even_after_binding_reversal(bindings):
    result = validator().validate(
        f"SELECT s.student_id,COUNT(*) AS fact_row_count {bindings} "
        "GROUP BY s.student_id ORDER BY COUNT(p.student_id)"
    )
    assert result.fact_table == "payments" and "ORDER BY fact_row_count" in result.statement


def test_star_both_verified_root_keys_count_the_same_matched_fact_rows():
    sql = (
        "SELECT s.student_id,c.course_id,COUNT(p.course_id) AS fact_row_count "
        "FROM uploaded_data.payments p INNER JOIN uploaded_data.students s "
        "ON p.student_id=s.student_id INNER JOIN uploaded_data.courses c "
        "ON p.course_id=c.course_id GROUP BY s.student_id,c.course_id "
        "ORDER BY COUNT(p.student_id)"
    )
    result = validator((PS, PC)).validate(sql)
    assert "COUNT(p.course_id) AS fact_row_count" in result.statement
    assert result.count_metrics[0].kind.value == "row_count"
    assert "ORDER BY fact_row_count" in result.statement


@pytest.mark.parametrize(
    "projection,suffix",
    [
        ("COUNT(*) AS fact_value_count", ""),
        ("SUM(p.amount) AS total", " ORDER BY COUNT(*)"),
        ("COUNT(*) AS fact_row_count", " HAVING COUNT(*)>0"),
        ("COUNT(*)+1 AS total", ""),
        ("COALESCE(COUNT(*),0) AS total", ""),
        ("COUNT(p.amount) AS fact_row_count", ""),
        ("COUNT(DISTINCT p.student_id) AS fact_value_count", ""),
        ("SUM(s.fee) AS total", ""),
        ("COUNT(*) FILTER(WHERE p.amount>0) AS fact_row_count", ""),
    ],
)
def test_hybrid_fake_drafts_stop_before_execution_grounding_or_retrieval(projection, suffix):
    gateway, executor, rag = Mock(), Mock(), Mock()
    sql = f"SELECT s.student_id,{projection} {CHAIN_ORDERS[0]} GROUP BY s.student_id" + suffix
    gateway.generate_structured.side_effect = [
        RouteDecision(route=RouteLabel.HYBRID, reason="Scripted offline"),
        SqlDraft(sql=sql),
    ]
    pipeline = TextToSqlPipeline(
        SqlGenerator(gateway, "2026-10-21", "Synthetic metadata"),
        validator(),
        executor,
        gateway,
    )
    service = DatasetChatService(
        QueryRouter(gateway, "Synthetic metadata"),
        pipeline,
        rag,
        HybridPipeline(pipeline, rag, gateway),
    )
    result = service.chat("Đối chiếu kết quả theo quy định trong tài liệu giả lập")
    assert result.route == RouteLabel.UNSUPPORTED
    assert result.sql is None and result.rows == [] and result.sources == []
    assert gateway.generate_structured.call_count == 2
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()
    rag.retrieve.assert_not_called()
