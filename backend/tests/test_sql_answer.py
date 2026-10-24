from decimal import Decimal
from unittest.mock import Mock

from app.text_to_sql.answer import compose_sql_answer
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
    assert "0.00" in result.answer and "NULL" in result.answer
    assert '"rows": số dòng nguồn' in result.answer
    assert '"present": số giá trị khác NULL' in result.answer
    assert "VND" not in result.answer
    gateway.generate_text.assert_not_called()


def test_neutral_table_preserves_large_numbers_null_and_does_not_invent_empty_rows():
    answer = compose_sql_answer([{"n": "9007199254740993", "x": Decimal("0.0000"), "y": None}], ())
    assert "9007199254740993" in answer and "0.0000" in answer and "NULL" in answer
    assert "dòng dữ liệu nào" in compose_sql_answer([], ())
