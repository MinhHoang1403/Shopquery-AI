"""HTTP contract tests for conversation and dataset management."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.conversations.repository import ConversationRecord, MessageRecord
from app.core.errors import ResourceNotFoundError
from app.datasets.parser import ColumnSpec
from app.datasets.repository import DatasetInfo, DatasetTableInfo
from app.main import app
from app.routing.router import RouteLabel
from app.routing.service import ChatResult

NOW = datetime(2026, 10, 14, tzinfo=UTC)


class FakeConversationRepository:
    def __init__(self) -> None:
        self.conversation_id = uuid4()
        self.title = "Cuộc trò chuyện mới"
        self.messages: list[MessageRecord] = []
        self.exists = True

    def _record(self, *, include_messages: bool = False) -> ConversationRecord:
        if not self.exists:
            raise ResourceNotFoundError("Không tìm thấy cuộc trò chuyện.")
        return ConversationRecord(
            conversation_id=self.conversation_id,
            title=self.title,
            dataset_id=None,
            dataset_name="Dữ liệu cửa hàng mẫu",
            created_at=NOW,
            updated_at=NOW,
            messages=tuple(self.messages) if include_messages else (),
        )

    def list(self, limit: int, offset: int) -> list[ConversationRecord]:
        del limit, offset
        return [self._record()] if self.exists else []

    def create(self, dataset_id: int | None) -> ConversationRecord:
        assert dataset_id is None
        self.exists = True
        return self._record()

    def get(self, conversation_id: UUID) -> ConversationRecord:
        if conversation_id != self.conversation_id:
            raise ResourceNotFoundError("Không tìm thấy cuộc trò chuyện.")
        return self._record(include_messages=True)

    def rename(self, conversation_id: UUID, title: str) -> ConversationRecord:
        self.get(conversation_id)
        self.title = title
        return self._record()

    def delete(self, conversation_id: UUID) -> None:
        self.get(conversation_id)
        self.exists = False

    def add_user_message(self, conversation_id: UUID, content: str) -> MessageRecord:
        self.get(conversation_id)
        self.title = content
        message = MessageRecord(len(self.messages) + 1, "user", content, None, NOW)
        self.messages.append(message)
        return message

    def add_response_message(
        self,
        conversation_id: UUID,
        *,
        content: str,
        response_metadata: dict[str, object],
        is_error: bool,
    ) -> MessageRecord:
        self.get(conversation_id)
        message = MessageRecord(
            len(self.messages) + 1,
            "error" if is_error else "assistant",
            content,
            response_metadata,
            NOW,
        )
        self.messages.append(message)
        return message


class FakeChatService:
    def chat(self, question: str) -> ChatResult:
        return ChatResult(
            answer=f"Đã phân tích: {question}",
            route=RouteLabel.SQL,
            sql="SELECT 1 AS total",
            rows=[{"total": 1}],
        )


def _dataset() -> DatasetInfo:
    return DatasetInfo(
        dataset_id=7,
        name="Doanh số 2026",
        original_filename="sales.csv",
        file_type="csv",
        row_count=2,
        column_count=2,
        created_at=NOW,
        table=DatasetTableInfo(
            display_name="sales",
            sheet_name=None,
            physical_table_name="dataset_fixture",
            columns=(
                ColumnSpec("Sản phẩm", "san_pham", "TEXT"),
                ColumnSpec("Doanh thu", "doanh_thu", "BIGINT"),
            ),
            row_count=2,
        ),
    )


class FakeDatasetRepository:
    def list(self) -> list[DatasetInfo]:
        return [_dataset()]

    def get(self, dataset_id: int) -> DatasetInfo:
        if dataset_id != 7:
            raise ResourceNotFoundError("Không tìm thấy bộ dữ liệu.")
        return _dataset()

    def preview_rows(self, dataset_id: int, limit: int = 10) -> list[dict[str, object]]:
        self.get(dataset_id)
        return [{"Sản phẩm": "Áo", "Doanh thu": 120_000}][:limit]


def test_conversation_crud_and_message_contract(monkeypatch) -> None:
    repository = FakeConversationRepository()
    monkeypatch.setattr("app.api.routes.build_conversation_repository", lambda: repository)
    monkeypatch.setattr("app.api.routes.build_chat_service", lambda settings: FakeChatService())
    client = TestClient(app)

    created = client.post("/api/conversations", json={})
    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]

    sent = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "Tổng doanh thu?"},
    )
    assert sent.status_code == 200
    assert sent.json()["assistant_message"]["response"]["rows"] == [{"total": 1}]

    restored = client.get(f"/api/conversations/{conversation_id}")
    assert [item["role"] for item in restored.json()["messages"]] == [
        "user",
        "assistant",
    ]

    renamed = client.patch(f"/api/conversations/{conversation_id}", json={"title": "Báo cáo tháng"})
    assert renamed.json()["title"] == "Báo cáo tháng"
    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 204
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_dataset_list_detail_and_scoped_chat(monkeypatch) -> None:
    repository = FakeDatasetRepository()
    monkeypatch.setattr("app.api.routes.build_dataset_repository", lambda: repository)
    monkeypatch.setattr(
        "app.api.routes.build_dataset_chat_service",
        lambda settings, context: FakeChatService(),
    )
    client = TestClient(app)

    listed = client.get("/api/datasets")
    assert listed.status_code == 200
    assert [item["kind"] for item in listed.json()] == ["default", "uploaded"]

    detail = client.get("/api/datasets/7")
    assert detail.json()["preview_rows"] == [{"Sản phẩm": "Áo", "Doanh thu": 120_000}]

    chat = client.post("/api/chat", json={"message": "Tổng doanh thu?", "dataset_id": 7})
    assert chat.status_code == 200
    assert chat.json()["route"] == "SQL"
    assert client.get("/api/datasets/99").status_code == 404


def test_dataset_preview_accepts_csv_and_rejects_unsafe_input() -> None:
    client = TestClient(app)

    preview = client.post(
        "/api/datasets/preview",
        files={"file": ("sales.csv", "Sản phẩm,Doanh thu\nÁo,120000\n", "text/csv")},
    )
    assert preview.status_code == 200
    assert preview.json()["columns"][1]["data_type"] == "BIGINT"
    assert preview.json()["rows"] == [{"Sản phẩm": "Áo", "Doanh thu": "120000"}]

    rejected = client.post(
        "/api/datasets/preview",
        files={"file": ("payload.exe", b"not allowed", "application/octet-stream")},
    )
    assert rejected.status_code == 422
    assert "CSV" in rejected.json()["detail"]


def test_dataset_preview_accepts_xlsx_and_selected_sheet() -> None:
    workbook = Workbook()
    first_sheet = workbook.active
    first_sheet.title = "Tổng quan"
    first_sheet.append(["Ghi chú"])
    first_sheet.append(["Không chọn sheet này"])
    sales_sheet = workbook.create_sheet("Doanh số")
    sales_sheet.append(["Sản phẩm", "Doanh thu"])
    sales_sheet.append(["Áo", 120_000])
    content = BytesIO()
    workbook.save(content)
    workbook.close()

    response = TestClient(app).post(
        "/api/datasets/preview",
        data={"sheet_name": "Doanh số"},
        files={
            "file": (
                "sales.xlsx",
                content.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["sheet_name"] == "Doanh số"
    assert response.json()["sheet_names"] == ["Tổng quan", "Doanh số"]
    assert response.json()["columns"][1]["data_type"] == "BIGINT"
    assert response.json()["rows"] == [{"Sản phẩm": "Áo", "Doanh thu": 120_000}]
