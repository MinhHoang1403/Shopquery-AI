"""Retry a complete read-only turn once, never individual generation stages."""

from collections.abc import Callable
from typing import Protocol

from app.ai.gemini import GenerationGateway
from app.ai.providers import build_generation_gateway, query_embedding_scope
from app.core.config import Settings
from app.core.diagnostics import attach_error_context, diagnosed, record_facts
from app.core.errors import ChatTurnError, ProviderError, ShopQueryError
from app.routing.service import ChatResult


class ChatPipeline(Protocol):
    def chat(self, question: str, *, current_question: str | None = None) -> ChatResult: ...


class ModelChatService:
    def __init__(
        self, settings: Settings, build_pipeline: Callable[[GenerationGateway], ChatPipeline]
    ) -> None:
        self._settings = settings
        self._build_pipeline = build_pipeline

    def _attempt(
        self,
        model_id: str,
        question: str,
        current_question: str | None = None,
    ) -> ChatResult:
        record_facts(model_id=model_id, used_model=model_id)
        gateway = build_generation_gateway(self._settings, model_id)
        try:
            return self._build_pipeline(gateway).chat(
                question,
                **({"current_question": current_question} if current_question is not None else {}),
            )
        finally:
            close = getattr(gateway, "close", None)
            if close:
                close()

    @diagnosed
    @query_embedding_scope()
    def chat(self, question: str, *, current_question: str | None = None) -> ChatResult:
        requested = self._settings.ai_default_model
        record_facts(model=requested, requested_model=requested, fallback_used=False)
        fallback = False
        fallback_reason = None
        fallback_context = None
        try:
            try:
                result = self._attempt(requested, question, current_question)
            except ProviderError as exc:
                if not (
                    requested == "inetcloud-knowledge"
                    and exc.fallback_allowed
                    and self._settings.ai_gemini_fallback_enabled
                    and self._settings.gemini_api_key
                ):
                    raise
                fallback = True
                fallback_context = attach_error_context(exc)
                category = fallback_context.error_category
                fallback_reason = (
                    f"primary_provider_{category}" if category else "primary_provider_unavailable"
                )
                record_facts(
                    fallback_error_context=fallback_context,
                    fallback_used=True,
                    fallback_error_category=category,
                )
                result = self._attempt("gemini", question, current_question)
        except ShopQueryError as exc:
            attach_error_context(exc)
            raise ChatTurnError(
                exc,
                requested,
                fallback_used=fallback,
                fallback_reason=fallback_reason,
                fallback_error_context=fallback_context,
            ) from exc
        result.requested_model = requested
        result.used_model = "gemini" if fallback else requested
        result.fallback_used = fallback
        result.fallback_reason = fallback_reason
        result.fallback_error_context = fallback_context
        record_facts(fallback_used=fallback, verification_status=result.verification_status)
        return result
