from decimal import Decimal
from unittest.mock import Mock

from app.text_to_sql.answer import ResultColumn, compose_sql_answer
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.pipeline import TextToSqlPipeline
from app.text_to_sql.query_plan import PlanExpression, PlanField, QueryPlan
from tests.test_workspace_prompts import tuition_context


def test_compiled_count_provenance_and_exact_rows_need_no_answer_generation():
    compiler = QueryCompiler(tuition_context())
    amount = next(k for k, (_, name) in compiler.references.columns.items() if name == "da_dong")
    plan = QueryPlan(
        source="t0",
        expressions=[
            PlanExpression(operation="row_count"),
            PlanExpression(operation="value_count", arguments=[amount]),
            PlanExpression(operation="sum", arguments=[amount]),
            PlanExpression(operation="avg", arguments=[amount]),
        ],
        fields=[
            PlanField(reference=f"e{i}", alias=alias)
            for i, alias in enumerate(("rows", "present", "total", "average"))
        ],
    )
    values = [{"rows": 3, "present": 2, "total": "0.00", "average": None}]
    gateway, executor = Mock(), Mock()
    executor.execute.return_value = values
    gateway.generate_text.side_effect = AssertionError("Unnecessary paid answer call")
    result = TextToSqlPipeline(
        Mock(generate=Mock(return_value=plan)), compiler, executor, gateway
    ).run("Tổng?")
    assert result.rows == values
    assert "**3 bản ghi**" in result.answer and "**Tổng Đã đóng** là **0,00**" in result.answer
    assert "**2 giá trị có dữ liệu**" in result.answer
    assert "**Trung bình Đã đóng** chưa có giá trị được ghi nhận" in result.answer
    assert "VND" not in result.answer
    gateway.generate_text.assert_not_called()


def test_neutral_table_preserves_large_numbers_null_and_does_not_invent_empty_rows():
    answer = compose_sql_answer([{"n": "9007199254740993", "x": Decimal("0.0000"), "y": None}], ())
    assert "9007199254740993" in answer and "Chưa có dữ liệu" in answer
    assert "Không tìm thấy" in compose_sql_answer([], ())


def test_scalar_display_and_empty_are_lossless_and_do_not_invent_units():
    columns = (ResultColumn(key="amount", label="Tổng", numeric=True),)
    assert "638.885.507,75" in compose_sql_answer([{"amount": "638885507.75"}], (), columns)
    assert "9.007.199.254.740.993" in compose_sql_answer(
        [{"amount": "9007199254740993"}], (), columns
    )
    assert "0,0000" in compose_sql_answer([{"amount": "0.0000"}], (), columns)
    assert "chưa có giá trị" in compose_sql_answer([{"amount": None}], ())
    assert "đồng" not in compose_sql_answer([{"vnd": "100.00"}], ())
    assert "24 kết quả" in compose_sql_answer([{"id": i} for i in range(24)], ())
