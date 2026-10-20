"""Public, capability-scoped guest API; never accepts personal resource IDs."""

import asyncio
import hmac
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.ai.providers import MODEL_LABELS, ModelId
from app.api.models import ChatResponse
from app.auth.repository import csrf_token
from app.core.client_ip import client_ip
from app.core.config import get_settings
from app.database.session import get_setup_engine
from app.datasets.relationships import MAX_RELATIONSHIPS, RelationshipRecord
from app.guest.limits import GuestControl
from app.guest.store import GuestContext, file_metadata, guest_store
from app.guest.worker import run_isolated

router = APIRouter(prefix="/api/guest")


def require_origin(request: Request) -> None:
    settings = get_settings()
    if not settings.guest_enabled:
        raise HTTPException(503, "Chế độ khách hiện đang tắt.")
    if (
        request.method not in {"GET", "HEAD"}
        and request.headers.get("origin") != settings.app_origin
    ):
        raise HTTPException(403, "Guest Origin validation failed.")


def require_guest(request: Request) -> GuestContext:
    require_origin(request)
    raw = request.headers.get("x-guest-token", "")
    context = guest_store().get(raw)
    if not hmac.compare_digest(request.headers.get("x-guest-csrf", ""), csrf_token(raw)):
        raise HTTPException(403, "Guest CSRF validation failed.")
    return context


CurrentGuest = Annotated[GuestContext, Depends(require_guest)]


def guest_control() -> GuestControl:
    return GuestControl(get_setup_engine(), get_settings())


def peer_ip(request: Request) -> str:
    return client_ip(request, get_settings())


def status(context: GuestContext) -> dict:
    settings = get_settings()
    return {
        "remaining": context.remaining,
        "ai_enabled": settings.guest_ai_enabled and settings.beta_provider_data_enabled,
        "ttl_seconds": settings.guest_session_seconds,
        "max_files": settings.guest_max_files,
        "max_file_bytes": settings.guest_max_file_bytes,
        "max_rows": settings.guest_max_rows,
        "max_columns": settings.guest_max_columns,
        "max_pages": settings.guest_max_pages,
        "max_session_bytes": settings.guest_max_session_bytes,
        "max_chunks": settings.guest_max_chunks,
        "files": [file_metadata(file) for file in context.files],
        "default_model": settings.ai_default_model,
        "models": [
            {
                "id": id,
                "label": label,
                "provider": "inetcloud" if id == "inetcloud-knowledge" else "gemini",
                "configured": bool(
                    settings.inetcloud_base_url
                    if id == "inetcloud-knowledge"
                    else settings.gemini_api_key
                ),
            }
            for id, label in MODEL_LABELS.items()
        ],
        "gemini_fallback_enabled": settings.ai_gemini_fallback_enabled,
        "sql_join_v1_enabled": settings.sql_join_v1_enabled,
    }


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GuestChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    model_id: ModelId | None = None

    @field_validator("message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must not be blank")
        return value.strip()


class FileOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    sheet_name: str | None = Field(default=None, max_length=120)


@router.post("/session")
def create_session(request: Request, body: EmptyRequest) -> dict:
    require_origin(request)
    if request.query_params:
        raise HTTPException(400, "Unexpected guest session parameters")
    settings = get_settings()
    guest_control().ip_rate(peer_ip(request), "session", settings.guest_sessions_per_ip_hour)
    raw, context = guest_store().create()
    return {**status(context), "token": raw, "csrf_token": csrf_token(raw)}


@router.get("/limits")
def limits(guest: CurrentGuest) -> dict:
    return status(guest)


@router.post("/reset", status_code=204)
def reset(guest: CurrentGuest, body: EmptyRequest) -> Response:
    guest_store().reset(guest)
    return Response(status_code=204)


async def process_file(
    request: Request, guest: GuestContext, options: FileOptions, commit: bool
) -> dict:
    settings = get_settings()
    control, store = guest_control(), guest_store()
    control.ip_rate(peer_ip(request), "preview", settings.guest_previews_per_ip_hour)
    with store.operation(guest), control.lease(guest.key, settings):
        if guest.parse_count >= settings.guest_previews_per_session:
            raise HTTPException(
                429,
                "Đã hết lượt xử lý tệp của phiên khách. Hãy bắt đầu phiên mới.",
                headers={"X-Guest-Limit": "preview"},
            )
        guest.parse_count += 1
        if guest.uploaded_count >= settings.guest_max_files:
            raise HTTPException(429, "Đã đạt giới hạn số tệp của phiên khách.")
        chunks, size = [], 0
        try:
            async with asyncio.timeout(settings.guest_parse_timeout_seconds):
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > settings.guest_max_file_bytes:
                        raise HTTPException(413, "Tệp vượt quá giới hạn dung lượng khách.")
                    chunks.append(chunk)
        except TimeoutError as exc:
            raise HTTPException(408, "Tải tệp quá thời gian cho phép.") from exc
        parsed = await run_in_threadpool(
            run_isolated,
            "parse",
            (options.filename, b"".join(chunks), options.sheet_name),
            settings,
            guest.cancelled,
        )
        store.ensure_active(guest)
        if commit:
            control.ip_rate(peer_ip(request), "upload", settings.guest_uploads_per_ip_hour)
            detected = []
            if settings.sql_join_v1_enabled and parsed.table and any(f.table for f in guest.files):
                detected = await run_in_threadpool(
                    run_isolated,
                    "detect_relationships",
                    (
                        list(guest.files) + [parsed],
                        parsed.file_id,
                        {
                            frozenset({r.source_table_id, r.target_table_id})
                            for r in guest.relationships
                        },
                    ),
                    settings,
                    guest.cancelled,
                )
            records = [
                RelationshipRecord(
                    **preview.model_dump(),
                    relationship_id=uuid4().hex,
                    origin="automatic",
                    confirmed=False,
                )
                for preview in detected
            ]
            if len(guest.relationships) + len(records) > MAX_RELATIONSHIPS:
                records = []
            store.add_file(guest, parsed, tuple(records))
        preview = {
            **file_metadata(parsed),
            "sheet_names": list(parsed.table.sheet_names) if parsed.table else [],
            "sheet_name": parsed.table.sheet_name if parsed.table else None,
            "rows": parsed.table.preview() if parsed.table else [],
            "warnings": list(parsed.table.warnings) if parsed.table else [],
        }
        return {"preview": preview, "status": status(guest)}


@router.post("/files/preview")
async def preview_file(
    request: Request, guest: CurrentGuest, options: Annotated[FileOptions, Query()]
):
    return await process_file(request, guest, options, False)


@router.post("/files")
async def add_file(request: Request, guest: CurrentGuest, options: Annotated[FileOptions, Query()]):
    return await process_file(request, guest, options, True)


@router.post("/chat")
def chat(request: Request, guest: CurrentGuest, body: GuestChatRequest) -> dict:
    settings = get_settings()
    if not settings.beta_provider_data_enabled or not settings.guest_ai_enabled:
        raise HTTPException(
            403, "AI dùng thử chưa được quản trị viên bật. Bạn vẫn có thể tải và xem trước tệp tạm."
        )
    if len(body.message) > settings.guest_max_prompt_characters:
        raise HTTPException(422, "Câu hỏi vượt giới hạn độ dài của phiên khách.")
    store, control = guest_store(), guest_control()
    with store.operation(guest), control.lease(guest.key, settings):
        if guest.remaining <= 0:
            store.consume_question(guest)
        control.ip_rate(peer_ip(request), "chat", settings.guest_chat_per_ip_hour)
        store.consume_question(guest)
        selected = settings.model_copy(
            update={"ai_default_model": body.model_id or settings.ai_default_model}
        )
        try:
            payload = (list(guest.files), body.message)
            if settings.sql_join_v1_enabled:
                payload += (tuple(guest.relationships),)
            result = run_isolated("chat", payload, selected, guest.cancelled)
        except HTTPException as exc:
            exc.headers = {**(exc.headers or {}), "X-Guest-Remaining": str(guest.remaining)}
            raise
        store.ensure_active(guest)
        response = ChatResponse(
            answer=result.answer,
            route=result.route,
            sql=result.sql,
            rows=result.rows,
            sources=[source.__dict__ for source in result.sources],
            requested_model=result.requested_model,
            used_model=result.used_model,
            fallback_used=result.fallback_used,
            fallback_reason=result.fallback_reason,
        )
        return {"response": response.model_dump(), "status": status(guest)}
