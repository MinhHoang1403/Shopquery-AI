"""Pydantic API contracts."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.ai.providers import ModelId
from app.core.errors import ErrorContext
from app.routing.hybrid_evidence import VerificationStatus
from app.routing.router import RouteLabel
from app.text_to_sql.answer import ResultColumn


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2_000)
    dataset_id: int | None = Field(default=None, ge=1)
    model_id: ModelId | None = None
    route_hint: Literal["SQL", "RAG", "HYBRID"] | None = None

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped


class SourceResponse(BaseModel):
    chunk_id: int
    source_file: str
    section_title: str
    content: str


class ChatResponse(BaseModel):
    answer: str
    route: RouteLabel | None
    sql: str | None = None
    rows: list[dict[str, JsonValue]] = Field(
        default_factory=list,
        description=(
            "NUMERIC values are lossless decimal strings; "
            "browser-safe INTEGER/COUNT remain integers, larger integers are exact digit strings; "
            "NULL remains null."
        ),
    )
    sources: list[SourceResponse] = Field(default_factory=list)
    error: str | None = None
    requested_model: ModelId | None = None
    used_model: ModelId | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    fallback_error_context: ErrorContext | None = None
    error_context: ErrorContext | None = None
    verification_status: VerificationStatus | None = None
    result_columns: list[ResultColumn] = Field(default_factory=list)
    answer_row_indices: list[Annotated[int, Field(strict=True, ge=0, lt=200)]] | None = Field(
        default=None, max_length=200
    )


class ModelOption(BaseModel):
    id: ModelId
    label: str
    provider: str
    configured: bool


class ModelsResponse(BaseModel):
    ai_enabled: bool = False
    default_model: ModelId
    models: list[ModelOption]
    gemini_fallback_enabled: bool


class HealthResponse(BaseModel):
    status: str
    service: str


class DatasetColumnResponse(BaseModel):
    source_name: str
    name: str
    data_type: str


class DatasetTableResponse(BaseModel):
    dataset_table_id: int | None
    display_name: str
    original_filename: str | None
    file_type: str | None
    sheet_name: str | None
    row_count: int
    column_count: int
    columns: list[DatasetColumnResponse] = Field(default_factory=list)


class DatasetDocumentResponse(BaseModel):
    document_id: int
    dataset_id: int
    original_filename: str
    file_type: str
    title: str
    chunk_count: int
    created_at: datetime


class DatasetTablePreviewResponse(DatasetTableResponse):
    rows: list[dict[str, JsonValue]]


class DatasetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        stripped = " ".join(value.split())
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class DatasetResponse(BaseModel):
    dataset_id: int | None
    kind: Literal["default", "uploaded"]
    name: str
    original_filename: str | None = None
    file_type: str | None = None
    sheet_name: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    columns: list[DatasetColumnResponse] = Field(default_factory=list)
    table_count: int = 0
    document_count: int = 0
    tables: list[DatasetTableResponse] = Field(default_factory=list)
    created_at: datetime | None = None


class DatasetPreviewResponse(BaseModel):
    filename: str
    file_type: str
    sheet_name: str | None
    sheet_names: list[str]
    row_count: int
    column_count: int
    columns: list[DatasetColumnResponse]
    rows: list[dict[str, JsonValue]] = Field(
        description="Decimal values are lossless strings, never converted to binary floats."
    )
    warnings: list[str]


class DatasetDetailResponse(DatasetResponse):
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: int | None = Field(default=None, ge=1)
    model_id: ModelId | None = None


class ConversationRenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    model_id: ModelId | None = None

    @field_validator("title")
    @classmethod
    def reject_blank_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = " ".join(value.split())
        if not stripped:
            raise ValueError("title must not be blank")
        return stripped

    @model_validator(mode="after")
    def require_change(self) -> "ConversationRenameRequest":
        if self.title is None and self.model_id is None:
            raise ValueError("title or model_id is required")
        return self


class ConversationSummaryResponse(BaseModel):
    conversation_id: UUID
    title: str
    dataset_id: int | None
    dataset_name: str
    created_at: datetime
    updated_at: datetime
    model_id: ModelId = "gemini"


class ConversationMessageResponse(BaseModel):
    message_id: int
    role: Literal["user", "assistant", "error"]
    content: str
    response: ChatResponse | None = None
    created_at: datetime


class ConversationDetailResponse(ConversationSummaryResponse):
    messages: list[ConversationMessageResponse]


class ConversationSendResponse(BaseModel):
    conversation: ConversationSummaryResponse
    user_message: ConversationMessageResponse
    assistant_message: ConversationMessageResponse


DatasetName = Annotated[str, Field(min_length=1, max_length=120)]
