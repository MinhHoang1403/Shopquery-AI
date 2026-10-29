"""Domain-independent workspace prompts and unchanged SQL boundaries."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.config import Settings
from app.core.errors import SqlUnsupportedError, SqlValidationError
from app.datasets.context import DatasetSqlContext, build_dataset_sql_context
from app.datasets.parser import ColumnSpec
from app.datasets.repository import DatasetInfo, DatasetTableInfo
from app.dependencies import _build_dataset_chat_service
from app.rag.pipeline import RagAnswerDraft, RagPipeline
from app.rag.repository import RetrievedChunk
from app.routing.hybrid import HybridAnswerDraft, HybridPipeline
from app.routing.router import QueryRouter, RouteLabel
from app.semantic.wire import TaskProposal
from app.text_to_sql.pipeline import SqlResult
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.query_plan import PlanDecision
from app.text_to_sql.validator import SqlValidator
from tests.hybrid_fixtures import explanation_draft
from tests.plan_fixtures import decision_from_sql
from tests.semantic_fixtures import proposal_for_evidence
from tests.test_three_table_join import PS, SC, TYPES


class RecordingGateway:
    def __init__(self, route: RouteLabel = RouteLabel.SQL) -> None:
        self.prompt = ""
        self.route = route

    def generate_structured(self, prompt: str, response_model: type[Any]) -> Any:
        self.prompt = prompt
        if response_model is TaskProposal:
            return proposal_for_evidence(
                {
                    "SQL": "tables",
                    "RAG": "documents",
                    "HYBRID": "both",
                    "UNSUPPORTED": "unavailable",
                }[self.route]
            )
        if response_model is PlanDecision:
            return decision_from_sql(
                "SELECT SUM(da_dong) FROM uploaded_data.tuition_fixture", prompt
            )
        if response_model is RagAnswerDraft:
            return RagAnswerDraft(answer="Ngưỡng nợ trên 1000000.", used_chunk_ids=[41])
        if response_model is HybridAnswerDraft:
            return explanation_draft(prompt, [41])
        raise AssertionError(response_model)


def tuition_context(document_count: int = 0) -> DatasetSqlContext:
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
        document_count=document_count,
    )
    return build_dataset_sql_context(dataset)


@pytest.mark.parametrize("count", [0, 1])
def test_router_context_reports_actual_uploaded_document_availability(count):
    context = tuition_context(count)
    gateway = RecordingGateway()
    QueryRouter(gateway, context.routing_context).route("Tra cứu tài liệu")
    assert f"Uploaded document count in this workspace: {count}" in gateway.prompt
    assert context.has_documents is bool(count)


def test_workspace_sql_constraints_do_not_forbid_table_document_comparisons() -> None:
    context = tuition_context(document_count=1)

    assert "Never JOIN tables" in context.schema_context
    assert context.routing_context is not None
    assert "SQL columns:" in context.routing_context
    assert "Uploaded document count in this workspace: 1" in context.routing_context
    assert "Never JOIN tables" not in context.routing_context
    assert "Choose exactly one allowed table" not in context.routing_context


def test_router_distinguishes_hybrid_aggregation_from_an_unsupported_table_join() -> None:
    gateway = RecordingGateway(RouteLabel.HYBRID)
    context = tuition_context(document_count=1)
    question = "Tổng học phí đã đóng có đạt ngưỡng quy định trong tài liệu không?"

    decision = QueryRouter(gateway, context.routing_context).route(question)

    assert decision.route == RouteLabel.HYBRID
    assert "combine needs SQL records and document" in gateway.prompt
    assert "policy alone defines" in gateway.prompt.replace("\n", " ")
    assert "Never guess a policy metric, threshold" in gateway.prompt


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

    decision = QueryRouter(gateway, context.routing_context).route(question)

    assert decision.route == route  # The stub verifies the contract, not live LLM accuracy.
    data, _ = json.JSONDecoder().raw_decode(gateway.prompt.split("Source/context data:\n", 1)[1])
    assert data["source_description"] == context.routing_context
    assert data["bounded_conversation_context"] == ""
    assert "Choose evidence, not topic or keywords" in gateway.prompt
    assert "Available routes: HYBRID, RAG, SQL, UNSUPPORTED" in (gateway.prompt)
    assert "Preserve any known user predicates" in gateway.prompt
    assert "Use unresolved for conditions you cannot represent" in gateway.prompt
    assert "Default demo store:" not in gateway.prompt
    assert gateway.prompt.endswith("Current request:\n" + question)


def test_uploaded_sql_prompt_has_no_default_store_schema_or_policy_requirements() -> None:
    gateway = RecordingGateway()
    context = tuition_context()

    QueryPlanner(gateway, "2026-10-01", context).generate("Học viên nào còn nợ học phí?")

    assert '"relationships": []' in gateway.prompt
    assert '"name": "tuition_fixture"' in gateway.prompt
    assert '"header": "Đã đóng"' in gateway.prompt
    assert "Schema IDs are the only allowed" in gateway.prompt
    assert "never return sql" in gateway.prompt.lower()
    assert "category_code belongs only to categories" not in gateway.prompt
    assert "include category_code and category_name" not in gateway.prompt
    assert "status is 'completed'" not in gateway.prompt
    assert "Asia/Ho_Chi_Minh" in gateway.prompt


def test_planner_grouping_keys_come_only_from_approved_dimension_targets():
    context = replace(
        tuition_context(),
        table_columns={table: set(columns) for table, columns in TYPES.items()},
        column_types=TYPES,
        allowed_schemas={table: "uploaded_data" for table in TYPES},
        approved_joins=(PS, SC),
    )
    prompts = []

    class Gateway:
        def generate_structured(self, prompt, response_model):
            prompts.append(prompt)
            return response_model(unsupported_reason="Contract capture only")

    planner = QueryPlanner(Gateway(), "2026-10-01", context)
    with pytest.raises(SqlUnsupportedError):
        planner.generate("So sánh các khóa học")
    catalog, _ = json.JSONDecoder().raw_decode(prompts[0].split("Authorized catalog JSON:\n", 1)[1])
    actual = {
        table["name"]: [planner.references.columns[key] for key in table["grouping_keys"]]
        for table in catalog["tables"]
    }
    assert actual == {
        "payments": [],
        "students": [("students", "student_id")],
        "courses": [("courses", "course_id")],
    }


def test_uploaded_router_receives_schema_through_dependency_construction(monkeypatch) -> None:
    monkeypatch.setattr("app.dependencies.get_readonly_engine", lambda: object())
    gateway = RecordingGateway(RouteLabel.UNSUPPORTED)
    context = tuition_context()

    service = _build_dataset_chat_service(Settings(_env_file=None), context, gateway)
    result = service.chat("Trường bị thiếu?")

    assert result.route == RouteLabel.UNSUPPORTED
    data, _ = json.JSONDecoder().raw_decode(gateway.prompt.split("Source/context data:\n", 1)[1])
    assert data["source_description"] == context.routing_context
    assert "Never JOIN tables" not in gateway.prompt


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
    def run(self, question: str, **kwargs) -> SqlResult:
        return SqlResult(
            answer="Rows only",
            sql="SELECT ma_hoc_vien, hoc_phi_phai_nop - da_dong AS con_no "
            "FROM uploaded_data.tuition_fixture",
            rows=[{"ma_hoc_vien": "HV02", "con_no": 1_500_000}],
        )


class TuitionRagPipeline:
    def retrieve(self, question: str) -> list[RetrievedChunk]:
        return [RetrievedChunk(41, "tuition_policy.md", "Nhắc phí", "Nợ trên 1000000.", 0.1)]


@pytest.mark.parametrize("joined", [False, True])
def test_hybrid_prompt_grounds_non_product_entities_in_rows_and_documents(joined: bool) -> None:
    class SqlPipeline(TuitionSqlPipeline):
        def run(self, question: str, **kwargs) -> SqlResult:
            result = super().run(question)
            result.fact_table = "synthetic_fact" if joined else None
            return result

    gateway = RecordingGateway()
    result = HybridPipeline(SqlPipeline(), TuitionRagPipeline(), gateway).run(
        "Học viên nào vượt ngưỡng nhắc phí trong tài liệu?"
    )

    assert result.sources[0].chunk_id == 41
    assert result.rows == [{"ma_hoc_vien": "HV02", "con_no": 1_500_000}]
    assert "For other domains, do not demand store" in gateway.prompt
    assert "HV02" in gateway.prompt
    assert "Nợ trên 1000000" in gateway.prompt
    assert "Cover each requested record or group separately" in gateway.prompt
    assert "COUNT provenance below is backend-derived" in gateway.prompt
    assert "non_null_value_count counts non-NULL source values" in gateway.prompt
    if joined:
        assert "counts do not count dimension entities" in gateway.prompt


def test_rag_prompt_accepts_non_commerce_document_evidence() -> None:
    gateway = RecordingGateway()
    chunks = TuitionRagPipeline().retrieve("Ngưỡng nhắc phí?")

    result = RagPipeline(None, gateway, None).answer_from_chunks("Ngưỡng nhắc phí?", chunks)

    assert result.sources[0].source_file == "tuition_policy.md"
    assert "any domain, not just commerce" in gateway.prompt
    assert "If evidence is insufficient, say so" in gateway.prompt
