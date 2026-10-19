"""Domain-independent workspace prompts and unchanged SQL boundaries."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.config import Settings
from app.core.errors import SqlValidationError
from app.datasets.context import DatasetSqlContext, build_dataset_sql_context
from app.datasets.parser import ColumnSpec
from app.datasets.repository import DatasetInfo, DatasetTableInfo
from app.dependencies import _build_dataset_chat_service
from app.rag.pipeline import RagAnswerDraft, RagPipeline
from app.rag.repository import RetrievedChunk
from app.routing.hybrid import HybridAnswerDraft, HybridPipeline
from app.routing.router import QueryRouter, RouteDecision, RouteLabel
from app.text_to_sql.generator import SqlDraft, SqlGenerator
from app.text_to_sql.pipeline import SqlResult
from app.text_to_sql.validator import SqlValidator


class RecordingGateway:
    def __init__(self, route: RouteLabel = RouteLabel.SQL) -> None:
        self.prompt = ""
        self.route = route

    def generate_structured(self, prompt: str, response_model: type[Any]) -> Any:
        self.prompt = prompt
        if response_model is RouteDecision:
            return RouteDecision(route=self.route, reason="fixture")
        if response_model is SqlDraft:
            return SqlDraft(sql="SELECT SUM(da_dong) FROM uploaded_data.tuition_fixture")
        if response_model is RagAnswerDraft:
            return RagAnswerDraft(answer="Ngưỡng nợ trên 1000000.", used_chunk_ids=[41])
        if response_model is HybridAnswerDraft:
            return HybridAnswerDraft(answer="HV02 còn nợ 1500000.", used_chunk_ids=[41])
        raise AssertionError(response_model)


def tuition_context() -> DatasetSqlContext:
    table = DatasetTableInfo(
        display_name="Học phí",
        sheet_name=None,
        physical_table_name="tuition_fixture",
        columns=(
            ColumnSpec("Mã học viên", "ma_hoc_vien", "TEXT"),
            ColumnSpec("Học phí phải nộp", "hoc_phi_phai_nop", "BIGINT"),
            ColumnSpec("Đã đóng", "da_dong", "BIGINT"),
        ),
        row_count=3,
        original_filename="tuition.csv",
    )
    dataset = DatasetInfo(
        dataset_id=45,
        name="Học phí giả lập",
        original_filename=None,
        file_type=None,
        row_count=None,
        column_count=None,
        created_at=datetime(2026, 10, 19, tzinfo=UTC),
        table=table,
    )
    return build_dataset_sql_context(dataset)


@pytest.mark.parametrize(
    ("question", "route"),
    [
        ("Tổng học phí đã đóng?", RouteLabel.SQL),
        ("Tổng giờ làm theo phòng ban?", RouteLabel.SQL),
        ("Tổng cước vận tải theo tuyến?", RouteLabel.SQL),
        ("Tổng điện tiêu thụ theo trạm?", RouteLabel.SQL),
        ("Tổng số mẫu theo thí nghiệm?", RouteLabel.SQL),
        ("Hạn đóng học phí trong tài liệu?", RouteLabel.RAG),
        ("Học viên nào vượt ngưỡng nhắc phí trong tài liệu?", RouteLabel.HYBRID),
        ("Thời tiết ngày mai?", RouteLabel.UNSUPPORTED),
    ],
)
def test_router_prompt_uses_selected_source_not_commerce_only(
    question: str, route: RouteLabel
) -> None:
    gateway = RecordingGateway(route)
    context = tuition_context()

    decision = QueryRouter(gateway, context.schema_context).route(question)

    assert decision.route == route  # The stub verifies the contract, not live LLM accuracy.
    assert context.schema_context in gateway.prompt
    assert "Do not reject a question merely because" in gateway.prompt
    assert "Available routes for the selected data source: HYBRID, RAG, SQL, UNSUPPORTED" in (
        gateway.prompt
    )
    assert "A numeric threshold explicitly given" in gateway.prompt
    assert "When a supplied schema clearly lacks a required field" in gateway.prompt
    assert "Default demo store:" not in gateway.prompt
    assert "Question: " + question in gateway.prompt


def test_uploaded_sql_prompt_has_no_default_store_schema_or_policy_requirements() -> None:
    gateway = RecordingGateway()
    context = tuition_context()

    SqlGenerator(gateway, "2026-10-01", context.schema_context).generate(
        "Học viên nào còn nợ học phí?"
    )

    assert context.schema_context in gateway.prompt
    assert "Never JOIN tables" in gateway.prompt
    assert "SQL table identifier (copy exactly): uploaded_data.tuition_fixture" in gateway.prompt
    assert "Display labels, worksheet names and file names are never SQL table identifiers" in (
        gateway.prompt
    )
    assert "Do not invent tables, columns" in gateway.prompt
    assert "category_code belongs only to categories" not in gateway.prompt
    assert "include category_code and category_name" not in gateway.prompt
    assert "status is 'completed'" not in gateway.prompt
    assert "Asia/Ho_Chi_Minh" in gateway.prompt


def test_uploaded_router_receives_schema_through_dependency_construction(monkeypatch) -> None:
    monkeypatch.setattr("app.dependencies.get_readonly_engine", lambda: object())
    gateway = RecordingGateway(RouteLabel.UNSUPPORTED)
    context = tuition_context()

    service = _build_dataset_chat_service(Settings(_env_file=None), context, gateway)
    result = service.chat("Trường bị thiếu?")

    assert result.route == RouteLabel.UNSUPPORTED
    assert context.schema_context in gateway.prompt


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM products",
        "SELECT * FROM uploaded_data.other_workspace",
        "SELECT product_name FROM uploaded_data.tuition_fixture",
        "SELECT a.da_dong FROM uploaded_data.tuition_fixture a "
        "JOIN uploaded_data.tuition_fixture b ON a.ma_hoc_vien = b.ma_hoc_vien",
        "DELETE FROM uploaded_data.tuition_fixture",
    ],
)
def test_generalized_prompts_do_not_expand_sql_permissions(sql: str) -> None:
    context = tuition_context()
    with pytest.raises(SqlValidationError):
        SqlValidator(context.table_columns, context.allowed_schemas, max_tables=1).validate(sql)


class TuitionSqlPipeline:
    def run(self, question: str) -> SqlResult:
        return SqlResult(
            answer="Rows only",
            sql="SELECT ma_hoc_vien, hoc_phi_phai_nop - da_dong AS con_no "
            "FROM uploaded_data.tuition_fixture",
            rows=[{"ma_hoc_vien": "HV02", "con_no": 1_500_000}],
        )


class TuitionRagPipeline:
    def retrieve(self, question: str) -> list[RetrievedChunk]:
        return [RetrievedChunk(41, "tuition_policy.md", "Nhắc phí", "Nợ trên 1000000.", 0.1)]


def test_hybrid_prompt_grounds_non_product_entities_in_rows_and_documents() -> None:
    gateway = RecordingGateway()
    result = HybridPipeline(TuitionSqlPipeline(), TuitionRagPipeline(), gateway).run(
        "Học viên nào vượt ngưỡng nhắc phí trong tài liệu?"
    )

    assert result.sources[0].chunk_id == 41
    assert result.rows == [{"ma_hoc_vien": "HV02", "con_no": 1_500_000}]
    assert "For other domains, do not demand store" in gateway.prompt
    assert "HV02" in gateway.prompt
    assert "Nợ trên 1000000" in gateway.prompt
    assert "Cover each requested record or group separately" in gateway.prompt


def test_rag_prompt_accepts_non_commerce_document_evidence() -> None:
    gateway = RecordingGateway()
    chunks = TuitionRagPipeline().retrieve("Ngưỡng nhắc phí?")

    result = RagPipeline(None, gateway, None).answer_from_chunks("Ngưỡng nhắc phí?", chunks)

    assert result.sources[0].source_file == "tuition_policy.md"
    assert "any domain, not just commerce" in gateway.prompt
    assert "If evidence is insufficient, say so" in gateway.prompt
