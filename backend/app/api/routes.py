"""FastAPI routes for chat, conversations, and managed datasets."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status

from app.api.models import (
    ChatRequest,
    ChatResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationMessageResponse,
    ConversationRenameRequest,
    ConversationSendResponse,
    ConversationSummaryResponse,
    DatasetColumnResponse,
    DatasetDetailResponse,
    DatasetPreviewResponse,
    DatasetResponse,
    HealthResponse,
    SourceResponse,
)
from app.conversations.repository import ConversationRecord, MessageRecord
from app.core.config import get_settings
from app.core.errors import (
    ResourceConflictError,
    ResourceNotFoundError,
    ShopQueryError,
    UploadValidationError,
)
from app.datasets.context import build_dataset_sql_context
from app.datasets.parser import ParsedTable, parse_tabular_file
from app.datasets.repository import DatasetInfo
from app.dependencies import (
    build_chat_service,
    build_conversation_repository,
    build_dataset_chat_service,
    build_dataset_repository,
)
from app.routing.service import ChatResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report API liveness without invoking Gemini or the full pipeline."""

    return HealthResponse(status="ok", service=get_settings().app_name)


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        if request.dataset_id is None:
            service = build_chat_service(get_settings())
        else:
            dataset = build_dataset_repository().get(request.dataset_id)
            service = build_dataset_chat_service(
                get_settings(), build_dataset_sql_context(dataset)
            )
        return _chat_response(service.chat(request.message))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShopQueryError as exc:
        return _chat_error(exc)


@router.get("/conversations", response_model=list[ConversationSummaryResponse])
def list_conversations(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationSummaryResponse]:
    repository = build_conversation_repository()
    return [_conversation_summary(item) for item in repository.list(limit, offset)]


@router.post(
    "/conversations",
    response_model=ConversationSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    request: ConversationCreateRequest,
) -> ConversationSummaryResponse:
    try:
        return _conversation_summary(
            build_conversation_repository().create(request.dataset_id)
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/conversations/{conversation_id}", response_model=ConversationDetailResponse
)
def get_conversation(conversation_id: UUID) -> ConversationDetailResponse:
    try:
        return _conversation_detail(build_conversation_repository().get(conversation_id))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/conversations/{conversation_id}", response_model=ConversationSummaryResponse
)
def rename_conversation(
    conversation_id: UUID, request: ConversationRenameRequest
) -> ConversationSummaryResponse:
    try:
        return _conversation_summary(
            build_conversation_repository().rename(conversation_id, request.title)
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete(
    "/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_conversation(conversation_id: UUID) -> Response:
    try:
        build_conversation_repository().delete(conversation_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationSendResponse,
)
def send_conversation_message(
    conversation_id: UUID, request: ChatRequest
) -> ConversationSendResponse:
    repository = build_conversation_repository()
    try:
        conversation = repository.get(conversation_id)
        user_message = repository.add_user_message(conversation_id, request.message)
        if conversation.dataset_id is None:
            service = build_chat_service(get_settings())
        else:
            dataset = build_dataset_repository().get(conversation.dataset_id)
            service = build_dataset_chat_service(
                get_settings(), build_dataset_sql_context(dataset)
            )
        try:
            response = _chat_response(service.chat(request.message))
        except ShopQueryError as exc:
            response = _chat_error(exc)
        assistant_message = repository.add_response_message(
            conversation_id,
            content=response.answer,
            response_metadata=response.model_dump(mode="json"),
            is_error=response.error is not None,
        )
        updated = repository.get(conversation_id)
        return ConversationSendResponse(
            conversation=_conversation_summary(updated),
            user_message=_message_response(user_message),
            assistant_message=_message_response(assistant_message),
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/datasets", response_model=list[DatasetResponse])
def list_datasets() -> list[DatasetResponse]:
    uploaded = [_dataset_response(item) for item in build_dataset_repository().list()]
    return [_default_dataset_response(), *uploaded]


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(dataset_id: int) -> DatasetDetailResponse:
    try:
        repository = build_dataset_repository()
        dataset = repository.get(dataset_id)
        return DatasetDetailResponse(
            **_dataset_response(dataset).model_dump(),
            preview_rows=repository.preview_rows(dataset_id),
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/datasets/{dataset_id}/preview", response_model=list[dict[str, object]]
)
def get_dataset_preview(
    dataset_id: int, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> list[dict[str, object]]:
    try:
        return build_dataset_repository().preview_rows(dataset_id, limit)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/datasets/preview", response_model=DatasetPreviewResponse)
async def preview_dataset(
    file: Annotated[UploadFile, File()],
    sheet_name: Annotated[str | None, Form()] = None,
) -> DatasetPreviewResponse:
    parsed = await _parse_upload(file, sheet_name)
    return _dataset_preview_response(parsed)


@router.post(
    "/datasets/import",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_dataset(
    file: Annotated[UploadFile, File()],
    dataset_name: Annotated[str, Form(min_length=1, max_length=120)],
    sheet_name: Annotated[str | None, Form()] = None,
) -> DatasetResponse:
    parsed = await _parse_upload(file, sheet_name)
    try:
        dataset = build_dataset_repository().create(dataset_name, parsed)
        return _dataset_response(dataset)
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _parse_upload(file: UploadFile, sheet_name: str | None) -> ParsedTable:
    settings = get_settings()
    content = await file.read(settings.upload_max_bytes + 1)
    try:
        return parse_tabular_file(
            file.filename or "",
            content,
            sheet_name=sheet_name,
            max_bytes=settings.upload_max_bytes,
            max_rows=settings.upload_max_rows,
            max_columns=settings.upload_max_columns,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()


def _chat_response(result: ChatResult) -> ChatResponse:
    return ChatResponse(
        answer=result.answer,
        route=result.route,
        sql=result.sql,
        rows=result.rows,
        sources=[
            SourceResponse.model_validate(source, from_attributes=True)
            for source in result.sources
        ],
    )


def _chat_error(exc: ShopQueryError) -> ChatResponse:
    logger.warning("Chat request could not be completed: %s", type(exc).__name__)
    return ChatResponse(
        answer="Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.",
        route=None,
        error=str(exc),
    )


def _conversation_summary(item: ConversationRecord) -> ConversationSummaryResponse:
    return ConversationSummaryResponse(
        conversation_id=item.conversation_id,
        title=item.title,
        dataset_id=item.dataset_id,
        dataset_name=item.dataset_name,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _conversation_detail(item: ConversationRecord) -> ConversationDetailResponse:
    return ConversationDetailResponse(
        **_conversation_summary(item).model_dump(),
        messages=[_message_response(message) for message in item.messages],
    )


def _message_response(item: MessageRecord) -> ConversationMessageResponse:
    response = (
        ChatResponse.model_validate(item.response_metadata)
        if item.response_metadata is not None
        else None
    )
    return ConversationMessageResponse(
        message_id=item.message_id,
        role=item.role,
        content=item.content,
        response=response,
        created_at=item.created_at,
    )


def _default_dataset_response() -> DatasetResponse:
    return DatasetResponse(
        dataset_id=None,
        kind="default",
        name="Dữ liệu cửa hàng mẫu",
    )


def _dataset_response(item: DatasetInfo) -> DatasetResponse:
    return DatasetResponse(
        dataset_id=item.dataset_id,
        kind="uploaded",
        name=item.name,
        original_filename=item.original_filename,
        file_type=item.file_type,
        sheet_name=item.table.sheet_name,
        row_count=item.row_count,
        column_count=item.column_count,
        columns=[DatasetColumnResponse(**column.as_dict()) for column in item.table.columns],
        created_at=item.created_at,
    )


def _dataset_preview_response(parsed: ParsedTable) -> DatasetPreviewResponse:
    return DatasetPreviewResponse(
        filename=parsed.filename,
        file_type=parsed.file_type,
        sheet_name=parsed.sheet_name,
        sheet_names=list(parsed.sheet_names),
        row_count=parsed.row_count,
        column_count=parsed.column_count,
        columns=[DatasetColumnResponse(**column.as_dict()) for column in parsed.columns],
        rows=parsed.preview(),
        warnings=list(parsed.warnings),
    )
