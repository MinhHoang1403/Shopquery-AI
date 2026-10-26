"""FastAPI routes for chat, conversations, and managed datasets."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError

from app.ai.gemini import GeminiGateway
from app.ai.providers import MODEL_LABELS
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
    DatasetCreateRequest,
    DatasetDetailResponse,
    DatasetDocumentResponse,
    DatasetPreviewResponse,
    DatasetResponse,
    DatasetTablePreviewResponse,
    DatasetTableResponse,
    HealthResponse,
    ModelOption,
    ModelsResponse,
    SourceResponse,
)
from app.auth.dependencies import CurrentUser
from app.auth.limits import allow_provider_data, resource_control
from app.conversations.context import contextual_question
from app.conversations.repository import ConversationRecord, ConversationRepository, MessageRecord
from app.core.config import get_settings
from app.core.diagnostics import attach_error_context, diagnosed, diagnostic_stage, record_facts
from app.core.errors import (
    ChatTurnError,
    ResourceConflictError,
    ResourceNotFoundError,
    ShopQueryError,
    UploadValidationError,
    error_message,
)
from app.datasets.parser import ParsedTable, parse_tabular_file
from app.datasets.repository import DatasetInfo, DatasetTableInfo
from app.dependencies import (
    build_chat_service,
    build_conversation_repository,
    build_dataset_chat_service,
    build_dataset_repository,
    build_document_repository,
    build_workspace_context,
)
from app.rag.repository import DatasetDocumentInfo
from app.rag.upload_parser import MAX_PDF_PAGES, parse_document_file
from app.routing.service import ChatResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/models", response_model=ModelsResponse)
def list_models(user: CurrentUser) -> ModelsResponse:
    settings = get_settings()
    return ModelsResponse(
        ai_enabled=settings.beta_provider_data_enabled,
        default_model=settings.ai_default_model,
        models=[
            ModelOption(
                id=model_id,
                label=label,
                provider="inetcloud" if model_id == "inetcloud-knowledge" else "gemini",
                configured=bool(settings.inetcloud_base_url)
                if model_id == "inetcloud-knowledge"
                else bool(settings.gemini_api_key),
            )
            for model_id, label in MODEL_LABELS.items()
        ],
        gemini_fallback_enabled=settings.ai_gemini_fallback_enabled,
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report API liveness without invoking Gemini or the full pipeline."""

    return HealthResponse(status="ok", service=get_settings().app_name)


@router.get("/uploads/limits")
def upload_limits(user: CurrentUser) -> dict:
    settings = get_settings()
    return {
        "max_file_bytes": settings.upload_max_bytes,
        "max_rows": settings.upload_max_rows,
        "max_columns": settings.upload_max_columns,
        "max_pdf_pages": MAX_PDF_PAGES,
        "provider_data_enabled": settings.beta_provider_data_enabled,
        "preview_per_hour": settings.beta_preview_per_user_hour,
        "upload_per_hour": settings.beta_upload_per_user_hour,
        "sql_join_v1_enabled": settings.sql_join_v1_enabled,
    }


@router.post("/chat", response_model=ChatResponse)
@diagnosed
def chat(user: CurrentUser, request: ChatRequest) -> ChatResponse:
    settings = get_settings()
    if request.model_id is not None:
        settings = settings.model_copy(update={"ai_default_model": request.model_id})
    record_facts(model=settings.ai_default_model)
    try:
        dataset = None
        if request.dataset_id is not None:
            repository = build_dataset_repository(user.user_id)
            with diagnostic_stage("workspace_binding"):
                dataset = repository.get(request.dataset_id)
        allow_provider_data()
        if dataset is None:
            _require_demo_data(user.user_id)
        with resource_control().work(user.user_id, "chat"):
            if dataset is None:
                service = build_chat_service(settings)
            else:
                service = build_dataset_chat_service(
                    settings,
                    build_workspace_context(settings, dataset, repository),
                )
            return _chat_response(service.chat(_routed_question(request, request.message)))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShopQueryError as exc:
        return _chat_error(exc, settings.ai_default_model)


@router.get("/conversations", response_model=list[ConversationSummaryResponse])
def list_conversations(
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationSummaryResponse]:
    repository = build_conversation_repository(user.user_id)
    return [_conversation_summary(item) for item in repository.list(limit, offset)]


@router.post(
    "/conversations",
    response_model=ConversationSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    user: CurrentUser,
    request: ConversationCreateRequest,
) -> ConversationSummaryResponse:
    try:
        return _conversation_summary(
            build_conversation_repository(user.user_id).create(
                request.dataset_id, request.model_id or get_settings().ai_default_model
            )
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(user: CurrentUser, conversation_id: UUID) -> ConversationDetailResponse:
    try:
        return _conversation_detail(
            build_conversation_repository(user.user_id).get(conversation_id)
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummaryResponse)
def rename_conversation(
    user: CurrentUser, conversation_id: UUID, request: ConversationRenameRequest
) -> ConversationSummaryResponse:
    try:
        repository = build_conversation_repository(user.user_id)
        if request.model_id is not None:
            repository.set_model(conversation_id, request.model_id)
        if request.title is None:
            return _conversation_summary(repository.get(conversation_id))
        return _conversation_summary(repository.rename(conversation_id, request.title))
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(user: CurrentUser, conversation_id: UUID) -> Response:
    try:
        build_conversation_repository(user.user_id).delete(conversation_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationSendResponse,
)
def send_conversation_message(
    user: CurrentUser, conversation_id: UUID, request: ChatRequest
) -> ConversationSendResponse:
    repository = build_conversation_repository(user.user_id)
    try:
        conversation = repository.get(conversation_id)
        if request.dataset_id is not None and request.dataset_id != conversation.dataset_id:
            build_dataset_repository(user.user_id).get(request.dataset_id)
            raise HTTPException(409, "Cuộc trò chuyện đang gắn với bộ dữ liệu khác.")
        if conversation.dataset_id is not None:
            build_dataset_repository(user.user_id).get(conversation.dataset_id)
        allow_provider_data()
        if conversation.dataset_id is None:
            _require_demo_data(user.user_id)
        with resource_control().work(user.user_id, "chat"):
            return _persist_chat_turn(repository, conversation, request, user.user_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@diagnosed
def _persist_chat_turn(
    repository: ConversationRepository,
    conversation: ConversationRecord,
    request: ChatRequest,
    user_id: UUID,
) -> ConversationSendResponse:
    conversation_id = conversation.conversation_id
    selected_model = request.model_id or conversation.model_id
    record_facts(model=selected_model)
    settings = get_settings().model_copy(update={"ai_default_model": selected_model})
    if request.model_id is not None:
        repository.set_model(conversation_id, selected_model)
    user_message = repository.add_user_message(conversation_id, request.message)
    try:
        if conversation.dataset_id is None:
            service = build_chat_service(settings)
        else:
            dataset_repository = build_dataset_repository(user_id)
            with diagnostic_stage("workspace_binding"):
                dataset = dataset_repository.get(conversation.dataset_id)
            service = build_dataset_chat_service(
                settings,
                build_workspace_context(settings, dataset, dataset_repository),
            )
        question = contextual_question(
            request.message, conversation, user_id, conversation.dataset_id
        )
        response = _chat_response(
            service.chat(
                _routed_question(request, question),
                current_question=request.message,
            )
        )
    except ShopQueryError as exc:
        response = _chat_error(exc, selected_model)
    assistant_message = repository.add_response_message(
        conversation_id,
        content=response.answer,
        response_metadata=response.model_dump(mode="json"),
        is_error=response.error is not None,
    )
    return ConversationSendResponse(
        conversation=_conversation_summary(repository.get(conversation_id)),
        user_message=_message_response(user_message),
        assistant_message=_message_response(assistant_message),
    )


@router.get("/datasets", response_model=list[DatasetResponse])
def list_datasets(user: CurrentUser) -> list[DatasetResponse]:
    repository = build_dataset_repository(user.user_id)
    uploaded = [_dataset_response(item) for item in repository.list()]
    return ([_default_dataset_response()] if repository.has_demo_data() else []) + uploaded


def _require_demo_data(user_id: UUID) -> None:
    if not build_dataset_repository(user_id).has_demo_data():
        raise HTTPException(
            409, "Chưa có dữ liệu. Hãy tạo bộ dữ liệu và tải nguồn lên trước khi hỏi."
        )


@router.post(
    "/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(user: CurrentUser, request: DatasetCreateRequest) -> DatasetResponse:
    try:
        with resource_control().work(user.user_id, "upload"):
            resource_control().storage(user.user_id, new_dataset=True)
            return _dataset_response(
                build_dataset_repository(user.user_id).create_workspace(request.name)
            )
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(
    user: CurrentUser,
    dataset_id: int,
    include_preview: bool = True,
) -> DatasetDetailResponse:
    try:
        repository = build_dataset_repository(user.user_id)
        dataset = repository.get(dataset_id)
        return DatasetDetailResponse(
            **_dataset_response(dataset).model_dump(),
            preview_rows=(
                repository.preview_rows(dataset_id) if include_preview and dataset.table else []
            ),
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/datasets/{dataset_id}/preview", response_model=list[dict[str, object]])
def get_dataset_preview(
    user: CurrentUser, dataset_id: int, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> list[dict[str, object]]:
    try:
        return build_dataset_repository(user.user_id).preview_rows(dataset_id, limit)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/datasets/{dataset_id}/tables/{table_id}/preview",
    response_model=DatasetTablePreviewResponse,
)
def get_dataset_table_preview(
    user: CurrentUser,
    dataset_id: int,
    table_id: int,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> DatasetTablePreviewResponse:
    try:
        with resource_control().work(user.user_id, "preview"):
            repository = build_dataset_repository(user.user_id)
            dataset = repository.get(dataset_id)
            table = next((t for t in dataset.tables if t.dataset_table_id == table_id), None)
            if table is None:
                raise ResourceNotFoundError("Không tìm thấy bảng trong bộ dữ liệu.")
            return DatasetTablePreviewResponse(
                **_dataset_table_response(table).model_dump(),
                rows=repository.preview_rows(dataset_id, limit, table_id),
            )
    except ResourceNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Chưa đọc được dữ liệu bảng. Vui lòng thử lại sau.") from exc


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    user: CurrentUser, dataset_id: int, delete_conversations: bool = False
) -> Response:
    try:
        build_dataset_repository(user.user_id).delete(
            dataset_id, delete_conversations=delete_conversations
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/datasets/{dataset_id}/tables/{table_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dataset_table(user: CurrentUser, dataset_id: int, table_id: int) -> Response:
    try:
        build_dataset_repository(user.user_id).delete_table(dataset_id, table_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/datasets/preview", response_model=DatasetPreviewResponse)
async def preview_dataset(
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    sheet_name: Annotated[str | None, Form()] = None,
) -> DatasetPreviewResponse:
    with resource_control().work(user.user_id, "preview"):
        parsed = await _parse_upload(file, sheet_name)
    return _dataset_preview_response(parsed)


@router.post(
    "/datasets/import",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_dataset(
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    dataset_name: Annotated[str, Form(min_length=1, max_length=120)],
    sheet_name: Annotated[str | None, Form()] = None,
) -> DatasetResponse:
    try:
        with resource_control().work(user.user_id, "upload"):
            resource_control().storage(user.user_id, new_dataset=True)
            parsed = await _parse_upload(file, sheet_name)
            dataset = build_dataset_repository(user.user_id).create(dataset_name, parsed)
        return _dataset_response(dataset)
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/datasets/{dataset_id}/tables", response_model=list[DatasetTableResponse])
def list_dataset_tables(user: CurrentUser, dataset_id: int) -> list[DatasetTableResponse]:
    try:
        return [
            _dataset_table_response(item)
            for item in build_dataset_repository(user.user_id).get(dataset_id).tables
        ]
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/datasets/{dataset_id}/tables/preview", response_model=DatasetPreviewResponse)
async def preview_dataset_table(
    user: CurrentUser,
    dataset_id: int,
    file: Annotated[UploadFile, File()],
    sheet_name: Annotated[str | None, Form()] = None,
) -> DatasetPreviewResponse:
    try:
        build_dataset_repository(user.user_id).get(dataset_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    with resource_control().work(user.user_id, "preview"):
        return _dataset_preview_response(await _parse_upload(file, sheet_name))


@router.post(
    "/datasets/{dataset_id}/tables/import",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_dataset_table(
    user: CurrentUser,
    dataset_id: int,
    file: Annotated[UploadFile, File()],
    display_name: Annotated[str | None, Form(max_length=120)] = None,
    sheet_name: Annotated[str | None, Form()] = None,
) -> DatasetResponse:
    try:
        repository = build_dataset_repository(user.user_id)
        repository.get(dataset_id)
        with resource_control().work(user.user_id, "upload"):
            resource_control().storage(user.user_id)
            parsed = await _parse_upload(file, sheet_name)
            dataset = repository.add_table(
                dataset_id,
                parsed,
                display_name,
                auto_relationships=get_settings().sql_join_v1_enabled,
            )
        return _dataset_response(dataset)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/datasets/{dataset_id}/documents",
    response_model=list[DatasetDocumentResponse],
)
def list_dataset_documents(user: CurrentUser, dataset_id: int) -> list[DatasetDocumentResponse]:
    try:
        return [
            _dataset_document_response(item)
            for item in build_document_repository(user.user_id).list_documents(dataset_id)
        ]
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/datasets/{dataset_id}/documents",
    response_model=DatasetDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset_document(
    user: CurrentUser, dataset_id: int, file: Annotated[UploadFile, File()]
) -> DatasetDocumentResponse:
    settings = get_settings()
    try:
        build_dataset_repository(user.user_id).get(dataset_id)
        content = await file.read(settings.upload_max_bytes + 1)
        parsed = parse_document_file(
            file.filename or "", content, max_bytes=settings.upload_max_bytes
        )
        allow_provider_data()
        with resource_control().work(user.user_id, "upload"):
            resource_control().storage(user.user_id)
            gateway = GeminiGateway(settings)
            try:
                item = build_document_repository(user.user_id).add_document(
                    dataset_id, parsed, gateway
                )
            finally:
                gateway.close()
        return _dataset_document_response(item)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ShopQueryError as exc:
        logger.warning("Document ingestion failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Không thể tạo embedding; tài liệu chưa được lưu.",
        ) from exc
    finally:
        await file.close()


@router.get(
    "/datasets/{dataset_id}/documents/{document_id}",
    response_model=DatasetDocumentResponse,
)
def get_dataset_document(
    user: CurrentUser, dataset_id: int, document_id: int
) -> DatasetDocumentResponse:
    try:
        return _dataset_document_response(
            build_document_repository(user.user_id).get_document(dataset_id, document_id)
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/datasets/{dataset_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dataset_document(user: CurrentUser, dataset_id: int, document_id: int) -> Response:
    try:
        build_document_repository(user.user_id).delete_document(dataset_id, document_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        requested_model=result.requested_model,
        used_model=result.used_model,
        fallback_used=result.fallback_used,
        fallback_reason=result.fallback_reason,
        fallback_error_context=result.fallback_error_context,
        verification_status=result.verification_status,
        sources=[
            SourceResponse.model_validate(source, from_attributes=True) for source in result.sources
        ],
    )


def _routed_question(request: ChatRequest, question: str) -> str:
    return f"/{request.route_hint.lower()} {question}" if request.route_hint else question


def _chat_error(exc: ShopQueryError, requested_model: str | None = None) -> ChatResponse:
    record_facts(final_status="failure")
    context = attach_error_context(exc)
    logger.warning("Chat request failed: %s", context.model_dump_json(exclude_none=True))
    message = error_message(context)
    return ChatResponse(
        answer=message,
        route=None,
        error=message,
        error_context=context,
        verification_status="refused" if context.attempted_route == "HYBRID" else None,
        requested_model=exc.requested_model if isinstance(exc, ChatTurnError) else requested_model,
        fallback_used=isinstance(exc, ChatTurnError) and exc.fallback_used,
        fallback_reason=(
            exc.fallback_reason if isinstance(exc, ChatTurnError) else None
        ),
        fallback_error_context=(
            exc.fallback_error_context if isinstance(exc, ChatTurnError) else None
        ),
    )


def _conversation_summary(item: ConversationRecord) -> ConversationSummaryResponse:
    return ConversationSummaryResponse(
        conversation_id=item.conversation_id,
        title=item.title,
        dataset_id=item.dataset_id,
        dataset_name=item.dataset_name,
        created_at=item.created_at,
        updated_at=item.updated_at,
        model_id=item.model_id,
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
    first = item.table
    return DatasetResponse(
        dataset_id=item.dataset_id,
        kind="uploaded",
        name=item.name,
        original_filename=item.original_filename,
        file_type=item.file_type,
        sheet_name=first.sheet_name if first else None,
        row_count=item.row_count,
        column_count=item.column_count,
        columns=(
            [DatasetColumnResponse(**column.as_dict()) for column in first.columns] if first else []
        ),
        table_count=item.table_count,
        document_count=item.document_count,
        tables=[_dataset_table_response(table) for table in item.tables],
        created_at=item.created_at,
    )


def _dataset_table_response(item: DatasetTableInfo) -> DatasetTableResponse:
    return DatasetTableResponse(
        dataset_table_id=item.dataset_table_id,
        display_name=item.display_name,
        original_filename=item.original_filename,
        file_type=item.file_type,
        sheet_name=item.sheet_name,
        row_count=item.row_count,
        column_count=len(item.columns),
        columns=[DatasetColumnResponse(**column.as_dict()) for column in item.columns],
    )


def _dataset_document_response(item: DatasetDocumentInfo) -> DatasetDocumentResponse:
    return DatasetDocumentResponse.model_validate(item, from_attributes=True)


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
