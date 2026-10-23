"""Stage evidence must be bounded, private and unable to change application results."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from app.core.diagnostics import diagnostic_request, diagnostic_stage, record_facts, relay_events
from app.core.errors import ResourceConflictError, SqlExecutionError, StructuredResponseError
from app.routing.router import QueryRouter, RouteDecision, RouteLabel
from app.routing.service import DatasetChatService
from tests.sql_validation_fixtures import FixtureGenerator, SqlFixture, ValidationPipeline
from tests.test_three_table_join import validator

BASE = (
    "SELECT s.student_id,s.name,SUM(p.amount) AS total,COUNT(*) AS fact_row_count "
    "FROM uploaded_data.payments p INNER JOIN uploaded_data.students s "
    "ON p.student_id=s.student_id GROUP BY s.student_id,s.name"
)


@pytest.mark.parametrize(
    "stage",
    [
        "router_unsupported",
        "generator_unsupported",
        "structured_output_invalid",
        "sql_parse_error",
        "column_resolution",
        "join_relationship",
        "join_key",
        "join_aggregate",
        "join_grain",
        "execution_guard",
        "sql_execution",
        "answer_grounding",
        "success",
    ],
)
def test_failure_stage_is_precise_and_has_no_raw_evidence(stage):
    gateway = Mock()
    gateway.generate_text.return_value = "Synthetic answer"
    sql = {
        "sql_parse_error": "DELETE FROM uploaded_data.payments",
        "column_resolution": BASE.replace("p.amount", "p.private_unknown"),
        "join_key": BASE.replace("p.student_id=s.student_id", "p.payment_id=s.student_id"),
        "join_aggregate": BASE.replace("SUM(p.amount)", "SUM(s.fee)"),
        "join_grain": BASE.replace("GROUP BY s.student_id,s.name", "GROUP BY s.name"),
    }.get(stage, BASE)

    def structured(prompt, schema):
        if schema is RouteDecision:
            if stage == "structured_output_invalid":
                raise StructuredResponseError("SENSITIVE provider text")
            return RouteDecision(
                route=RouteLabel.UNSUPPORTED if stage == "router_unsupported" else RouteLabel.SQL,
                reason="Synthetic",
            )
        return SqlFixture(
            sql=sql,
            unsupported_reason="private refusal" if stage == "generator_unsupported" else None,
        )

    gateway.generate_structured.side_effect = structured
    executor = Mock()
    executor.execute.return_value = [{"total": "0.00", "fact_row_count": 1}]
    if stage == "sql_execution":
        executor.execute.side_effect = SqlExecutionError("SENSITIVE executor detail")
    if stage == "answer_grounding":
        gateway.generate_text.side_effect = RuntimeError("SENSITIVE answer detail")

    @contextmanager
    def guard(_):
        if stage == "execution_guard":
            raise ResourceConflictError("SENSITIVE stale metadata")
        yield

    checked = validator(
        relations=() if stage == "join_relationship" else validator()._approved_joins
    )
    pipeline = ValidationPipeline(
        FixtureGenerator(gateway, "2026-10-20", "Synthetic schema"),
        checked,
        executor,
        gateway,
        guard,
    )
    service = DatasetChatService(QueryRouter(gateway, "Synthetic"), pipeline, None, None)
    with diagnostic_request() as trace:
        record_facts(model="gemini", allowed_tables=3, approved_edges=2)
        try:
            result = service.chat("SENSITIVE user question")
        except (RuntimeError, SqlExecutionError, ResourceConflictError, StructuredResponseError):
            record_facts(final_status="failure")
            assert stage in {
                "answer_grounding",
                "sql_execution",
                "execution_guard",
                "structured_output_invalid",
            }
        except Exception:
            assert stage in {"sql_parse_error", "column_resolution"}
            record_facts(final_status="failure")
        else:
            assert result.route == (
                RouteLabel.SQL if stage == "success" else RouteLabel.UNSUPPORTED
            )
    assert len({e["correlation_id"] for e in trace.events}) == 1
    assert all(e["allowed_tables"] == 3 and e["approved_edges"] == 2 for e in trace.events)
    assert "SENSITIVE" not in str(trace.events) and "SELECT" not in str(trace.events)
    assert "private refusal" not in str(trace.events)
    if stage not in {"success", "router_unsupported"}:
        assert any(e["stage"] == stage and e["status"] == "failure" for e in trace.events)
    if stage not in {"success", "answer_grounding", "sql_execution"}:
        executor.execute.assert_not_called()
    if stage == "success":
        assert trace.events[-1]["execution_reached"] and trace.events[-1]["sql_validated"]
        assert trace.events[-1]["result_rows"] == 1


def test_telemetry_failure_does_not_fail_request_and_arbitrary_fields_are_discarded(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("logger unavailable")

    monkeypatch.setattr("app.core.diagnostics.logger.info", fail)
    with diagnostic_request() as trace:
        record_facts(model="secret", route="raw SQL", question="sensitive", allowed_tables=2)
        for _ in range(100):
            with diagnostic_stage("schema_metadata"):
                pass
    assert len(trace.events) == 64
    assert "sensitive" not in str(trace.events)
    assert trace.events[0]["model"] is None and trace.events[0]["route"] is None


def test_diagnostic_requests_are_isolated_across_concurrent_workers():
    def run(index):
        with diagnostic_request() as trace:
            record_facts(result_rows=index)
        return trace

    with ThreadPoolExecutor(max_workers=4) as pool:
        traces = list(pool.map(run, range(8)))
    assert len({t.correlation_id for t in traces}) == 8
    assert [t.events[-1]["result_rows"] for t in traces] == list(range(8))


def test_worker_events_preserve_correlation_and_parent_facts(caplog):
    with diagnostic_request() as parent:
        event = {
            "correlation_id": parent.correlation_id,
            "stage": "sql_execution",
            "status": "success",
            "reason": "ok",
            "duration_ms": 1,
            "model": "gemini",
            "route": "SQL",
            "allowed_tables": 3,
            "approved_edges": 2,
            "sql_validated": True,
            "execution_reached": True,
            "result_rows": 2,
        }
        with caplog.at_level("INFO", logger="app.core.diagnostics"):
            relay_events([event])
    assert parent.events[-1]["result_rows"] == 2
    assert parent.events[-1]["sql_validated"]
    assert parent.correlation_id in caplog.text


@pytest.mark.usefixtures("contract_session")
def test_api_correlation_header_and_failure_summary_do_not_expose_question(monkeypatch, caplog):
    import json

    from app.main import app
    from tests.auth_helpers import TestClient
    from tests.test_api import FailingChatService

    monkeypatch.setattr("app.api.routes.build_chat_service", lambda settings: FailingChatService())
    with caplog.at_level("INFO", logger="app.core.diagnostics"):
        response = TestClient(app).post("/api/chat", json={"message": "PRIVATE question"})
    events = [
        json.loads(record.getMessage().removeprefix("pipeline_diagnostic "))
        for record in caplog.records
        if record.getMessage().startswith("pipeline_diagnostic ")
    ]
    assert response.status_code == 200
    assert len(response.headers["X-Request-ID"]) == 32
    assert {event["correlation_id"] for event in events} == {response.headers["X-Request-ID"]}
    assert events[-1]["status"] == "failure"
    assert "PRIVATE question" not in caplog.text
