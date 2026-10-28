"""Prompt and refusal regressions from bounded synthetic JOIN acceptance."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from app.core.errors import SqlUnsupportedError
from app.datasets.context import build_dataset_sql_context
from app.datasets.parser import ColumnSpec
from app.datasets.repository import DatasetInfo, DatasetTableInfo
from app.routing.router import RouteLabel
from app.routing.service import DatasetChatService
from app.text_to_sql.join_policy import ApprovedJoin
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.query_plan import PlanDecision, PlanField, QueryPlan
from app.text_to_sql.validator import SqlValidator
from tests.test_dataset_routing import FakeRouter
from tests.test_workspace_prompts import tuition_context

DEFAULT_MESSAGE = "Chưa thể xử lý câu hỏi này chính xác trong phạm vi hỗ trợ hiện tại."
RELATIONSHIP_MESSAGE = (
    "Mình chưa tìm thấy liên kết phù hợp giữa các bảng. "
    "Bạn có thể thiết lập trong Quản lý dữ liệu → Liên kết bảng."
)
CALCULATION_MESSAGE = "Chưa thể xử lý phép tính này chính xác. Bạn có thể xem dữ liệu liên quan."


def test_join_prompt_includes_exact_from_fragment_even_when_dimension_is_listed_first() -> None:
    base = tuition_context()
    dimension = DatasetTableInfo(
        "Sinh viên",
        None,
        "students",
        (
            ColumnSpec("Mã học viên", "student_id", "BIGINT"),
            ColumnSpec("Tên", "name", "TEXT"),
        ),
        2,
    )
    fact = replace(
        dimension,
        display_name="Thanh toán",
        physical_table_name="payments",
        columns=(dimension.columns[0], ColumnSpec("Đã đóng", "amount", "NUMERIC")),
        row_count=3,
    )
    dataset = DatasetInfo(
        9,
        "Synthetic",
        None,
        None,
        None,
        None,
        datetime.now(UTC),
        dimension,
        tables=(dimension, fact),
    )
    relation = ApprovedJoin("confirmed", "payments", "student_id", "students", "student_id", "rev")
    context = build_dataset_sql_context(
        dataset, schema_name="pg_temp", approved_joins=(relation,), join_v1_enabled=True
    )
    gateway = Mock()
    gateway.generate_structured.return_value = PlanDecision(
        plan=QueryPlan(source="t0", fields=[PlanField(alias="n", aggregate="row_count")])
    )
    QueryPlanner(gateway, "2026-10-20", context).generate("Tổng theo học viên?")
    prompt = gateway.generate_structured.call_args.args[0]
    assert '"source": "t0.c' in prompt and '"target": "t1.c' in prompt
    assert "source fact to target dimension" in prompt
    assert "FROM pg_temp.payments" not in base.schema_context


@pytest.mark.parametrize("route", [RouteLabel.SQL, RouteLabel.HYBRID])
def test_unclassified_generator_refusal_does_not_claim_a_missing_relationship(
    route: RouteLabel,
) -> None:
    pipeline = Mock()
    pipeline.run.side_effect = SqlUnsupportedError("private raw reason or literal")
    result = DatasetChatService(FakeRouter(route), pipeline, pipeline, pipeline).chat("Câu hỏi")
    assert result.answer == DEFAULT_MESSAGE
    assert result.route == RouteLabel.UNSUPPORTED
    assert result.sql is None and result.rows == [] and result.sources == []


def test_empty_workspace_uses_data_message_without_join_jargon() -> None:
    result = DatasetChatService(None, None, None, None).chat("Tổng số đơn hàng?")
    assert result.answer == (
        "Chưa có đủ dữ liệu để trả lời câu hỏi này. Bạn hãy kiểm tra các tệp đã tải lên nhé."
    )


@pytest.mark.parametrize("route", [RouteLabel.SQL, RouteLabel.HYBRID])
@pytest.mark.parametrize(
    "reason,message",
    [
        ("relationship", RELATIONSHIP_MESSAGE),
        ("calculation", CALCULATION_MESSAGE),
    ],
)
def test_verified_sql_refusal_reason_maps_to_friendly_answer(
    route: RouteLabel,
    reason: str,
    message: str,
) -> None:
    pipeline = Mock()
    pipeline.run.side_effect = SqlUnsupportedError("developer detail", reason=reason)
    result = DatasetChatService(FakeRouter(route), pipeline, pipeline, pipeline).chat("Câu hỏi")
    assert result.answer == message
    assert result.rows == [] and result.sql is None and result.sources == []


def test_observed_gemini_reverse_join_is_canonicalized_with_the_approved_fact() -> None:
    relation = ApprovedJoin("r", "table_2", "student_id", "table_1", "student_id", "revision")
    validator = SqlValidator(
        {"table_1": {"student_id", "name"}, "table_2": {"student_id", "amount"}},
        {"table_1": "pg_temp", "table_2": "pg_temp"},
        max_tables=2,
        approved_joins=(relation,),
        join_v1_enabled=True,
        column_types={"table_2": {"amount": "NUMERIC"}},
    )
    observed = (
        "SELECT t1.name AS name, SUM(t2.amount) AS total, COUNT(*) AS fact_row_count "
        "FROM pg_temp.table_1 AS t1 INNER JOIN pg_temp.table_2 AS t2 "
        "ON t2.student_id = t1.student_id GROUP BY t1.student_id, t1.name ORDER BY t1.name"
    )
    validated = validator.validate(observed)
    assert "FROM pg_temp.table_2 AS t2 INNER JOIN pg_temp.table_1 AS t1" in validated.statement
    assert validated.fact_table == "table_2"
    assert validated.relationship_id == "r"
