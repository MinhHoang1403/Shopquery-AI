from dataclasses import replace
from decimal import Decimal

import pytest

from app.api.models import ChatResponse
from app.api.routes import _chat_response
from app.routing.router import RouteLabel
from app.routing.service import ChatResult
from app.text_to_sql.answer import ResultColumn, compose_sql_answer
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.query_plan import PlanField, QueryPlan
from tests.test_query_compiler import field
from tests.test_workspace_prompts import tuition_context


def test_presentation_metadata_comes_from_compiler_not_alias_or_value():
    context = tuition_context()
    compiler = QueryCompiler(context)
    amount = field(compiler, "tuition_fixture", "da_dong")
    plain = compiler.compile(
        QueryPlan(source="t0", fields=[PlanField(reference=amount, alias="total_money_vnd")])
    )
    # An unaggregated BIGINT might be a code. Its spelling does not prove a metric/unit.
    assert not plain.result_columns[0].numeric
    total = compiler.compile(
        QueryPlan(
            source="t0", fields=[PlanField(reference=amount, alias="anything", aggregate="sum")]
        )
    )
    assert total.result_columns[0].numeric
    assert total.result_columns[0].label == "Anything"
    context = replace(context, column_headers={"tuition_fixture": {"da_dong": "Số tiền đã đóng"}})
    registered = QueryCompiler(context).compile(
        QueryPlan(source="t0", fields=[PlanField(reference=amount, alias="x")])
    )
    assert registered.result_columns[0].label == "Số tiền đã đóng"


@pytest.mark.parametrize("size", [12, 16, 24, 200])
def test_multirow_summary_does_not_fabricate_totals_or_require_opening_detail(size):
    rows = [{"name": f"Mục {i}", "value": "0.00"} for i in range(size)]
    answer = compose_sql_answer(rows, ())
    assert f"{size} kết quả" in answer
    assert "bảng dữ liệu" not in answer and "tổng" not in answer


def test_scalar_metadata_preserves_identifiers_precision_null_and_safe_markdown():
    columns = (ResultColumn(key="sum", label="Tổng", numeric=True),)
    assert "56.531.054,50" in compose_sql_answer([{"sum": "56531054.50"}], (), columns)
    assert "1.000.000,00" in compose_sql_answer([{"sum": Decimal("1000000.00")}], (), columns)
    assert "000123" in compose_sql_answer([{"id": "000123"}], ())
    assert "20261026" in compose_sql_answer([{"date_code": 20261026}], ())
    assert "20.261.026" not in compose_sql_answer([{"date_code": 20261026}], ())
    assert "[x](https" not in compose_sql_answer([{"name": "[x](https://example.com)"}], ())
    assert "Không tìm thấy" in compose_sql_answer([], ())
    assert "chưa có giá trị" in compose_sql_answer([{"sum": None}], (), columns)


def test_metadata_roundtrip_keeps_verified_classification_and_legacy_history():
    result = ChatResult(
        "Đạt",
        RouteLabel.HYBRID,
        rows=[{"total": "0.00"}],
        verification_status="verified_classification",
        answer_row_indices=(0,),
        result_columns=(ResultColumn(key="total", label="Tổng", numeric=True),),
    )
    response = _chat_response(result)
    restored = ChatResponse.model_validate_json(response.model_dump_json())
    assert restored.result_columns == response.result_columns
    assert restored.rows == result.rows
    assert restored.verification_status == "verified_classification"
    assert restored.answer_row_indices == [0]
    assert ChatResponse(answer="Cũ", route="SQL").result_columns == []
