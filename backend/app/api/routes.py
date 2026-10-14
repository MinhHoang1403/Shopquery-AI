"""FastAPI routes with sanitized expected-error responses."""

import logging

from fastapi import APIRouter

from app.api.models import ChatRequest, ChatResponse, HealthResponse, SourceResponse
from app.core.config import get_settings
from app.core.errors import ShopQueryError
from app.dependencies import build_chat_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report API liveness without invoking Gemini or the full pipeline."""

    return HealthResponse(status="ok", service=get_settings().app_name)


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = build_chat_service(get_settings()).chat(request.message)
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
    except ShopQueryError as exc:
        logger.warning("Chat request could not be completed: %s", type(exc).__name__)
        return ChatResponse(
            answer="Không thể hoàn tất câu hỏi bằng dữ liệu hiện có.",
            route=None,
            error=str(exc),
        )
