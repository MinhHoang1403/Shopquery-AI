"""Retry a complete read-only turn once, never individual generation stages."""

from collections.abc import Callable
from typing import Protocol

from app.ai.gemini import GenerationGateway
from app.ai.providers import build_generation_gateway
from app.core.config import Settings
from app.core.diagnostics import attach_error_context, diagnosed, record_facts
from app.core.errors import ChatTurnError, ProviderError, ShopQueryError
from app.routing.service import ChatResult


class ChatPipeline(Protocol):
    def chat(self, question: str) -> ChatResult: ...


class ModelChatService:
    def __init__(
        self, settings: Settings, build_pipeline: Callable[[GenerationGateway], ChatPipeline]
    ) -> None:
        self._settings = settings
        self._build_pipeline = build_pipeline

    def _attempt(self, model_id: str, question: str) -> ChatResult:
        gateway = build_generation_gateway(self._settings, model_id)
        try:
            return self._build_pipeline(gateway).chat(question)
        finally:
            close = getattr(gateway, "close", None)
            if close:
                close()

    @diagnosed
    def chat(self, question: str) -> ChatResult:
        requested = self._settings.ai_default_model
        record_facts(model=requested)
        fallback = False
        try:
            try:
                result = self._attempt(requested, question)
            except ProviderError as exc:
                if not (
                    requested == "inetcloud-knowledge"
                    and exc.fallback_allowed
                    and self._settings.ai_gemini_fallback_enabled
                    and self._settings.gemini_api_key
                ):
                    raise
                fallback = True
                result = self._attempt("gemini", question)
        except ShopQueryError as exc:
            attach_error_context(exc)
            raise ChatTurnError(exc, requested, fallback_used=fallback) from exc
        result.requested_model = requested
        result.used_model = "gemini" if fallback else requested
        result.fallback_used = fallback
        result.fallback_reason = "primary_provider_unavailable" if fallback else None
        return result
