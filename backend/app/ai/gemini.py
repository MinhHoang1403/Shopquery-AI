"""Small Google GenAI SDK adapter with validated structured outputs."""

import json
import logging
import math
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.diagnostics import record_provider_call, record_provider_tokens
from app.core.errors import (
    TRANSIENT_PROVIDER_STATUSES,
    ConfigurationError,
    ErrorContext,
    ModelResponseError,
    ProviderError,
    StructuredResponseError,
    conversion_context,
    provider_category,
    validation_context,
)
from app.core.observability import provider_observation
from app.text_to_sql.generation_contract import GENERATION_INSTRUCTIONS, GenerationDecision
from app.text_to_sql.query_plan import PlanDecision

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)
TRANSIENT_HTTP_STATUS_CODES = list(TRANSIENT_PROVIDER_STATUSES)
logger = logging.getLogger(__name__)


def _without_additional_properties(value: Any) -> Any:
    """The native Schema endpoint rejects this keyword; Pydantic still forbids extras."""
    if isinstance(value, dict):
        return {
            key: _without_additional_properties(item)
            for key, item in value.items()
            if key != "additionalProperties"
        }
    if isinstance(value, list):
        return [_without_additional_properties(item) for item in value]
    return value


def _generation_schema(value: Any) -> Any:
    """Bound output locally; avoid multiplying grammar states with array/string bounds."""
    if isinstance(value, dict):
        return {
            key: _generation_schema(item)
            for key, item in value.items()
            if key
            not in {
                "additionalProperties",
                "minItems",
                "maxItems",
                "minLength",
                "maxLength",
                "minimum",
                "maximum",
            }
        }
    if isinstance(value, list):
        return [_generation_schema(item) for item in value]
    return value


class GenerationGateway(Protocol):
    def generate_structured(
        self, prompt: str, response_model: type[StructuredModel]
    ) -> StructuredModel: ...

    def generate_text(self, prompt: str) -> str: ...


class EmbeddingGateway(Protocol):
    def embed_query(self, content: str) -> list[float]: ...

    def embed_document(self, title: str, content: str) -> list[float]: ...


class GeminiGateway:
    """Synchronous Gemini gateway used by the request-oriented backend."""

    model_id = "gemini"

    def close(self) -> None:
        self._client.close()

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise ConfigurationError("GEMINI_API_KEY is required for AI generation and embeddings")
        self._settings = settings
        self._client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=settings.gemini_request_timeout_ms,
                retry_options=types.HttpRetryOptions(
                    attempts=settings.gemini_retry_attempts,
                    http_status_codes=TRANSIENT_HTTP_STATUS_CODES,
                ),
            ),
        )

    def generate_structured(
        self, prompt: str, response_model: type[StructuredModel]
    ) -> StructuredModel:
        wire_model = GenerationDecision if response_model is PlanDecision else response_model
        prompt_suffix = GENERATION_INSTRUCTIONS if wire_model is GenerationDecision else ""
        try:
            config = types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=(
                    _generation_schema(wire_model.model_json_schema())
                    if wire_model is GenerationDecision
                    else _without_additional_properties(wire_model.model_json_schema())
                ),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise self._structured_error("schema_preparation", "sdk_preparation", exc) from exc
        response = self._request(
            "generation",
            lambda: self._client.models.generate_content(
                model=self._settings.gemini_generation_model,
                contents=prompt + prompt_suffix,
                config=config,
            ),
        )
        refused = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION"}
        if any(
            getattr(candidate, "finish_reason", None) in refused
            for candidate in (getattr(response, "candidates", None) or [])
        ):
            raise ProviderError(
                "Gemini declined the response",
                error_context=self._context(
                    "generation", phase="response", error_category="model_refusal"
                ),
            )
        try:
            payload = json.loads(response.text)
        except (ValueError, TypeError) as exc:
            raise self._structured_error("json_decode", "invalid_json", exc) from exc
        try:
            parsed = wire_model.model_validate(payload)
        except ValidationError as exc:
            raise self._structured_error("wire_validation", "wire_validation", exc) from exc
        try:
            if isinstance(parsed, GenerationDecision):
                return response_model.model_validate(parsed.decision())
            return response_model.model_validate(parsed)
        except (ValidationError, ValueError, TypeError) as exc:
            raise self._structured_error("domain_conversion", "contract_conversion", exc) from exc

    def _context(self, operation: str, **details: Any) -> ErrorContext:
        return ErrorContext(
            provider="gemini",
            operation=operation,
            attempt=1 if self._settings.gemini_retry_attempts == 1 else None,
            **details,
        )

    def _structured_error(
        self, phase: str, category: str, exc: Exception
    ) -> StructuredResponseError:
        return StructuredResponseError(
            "Gemini returned an invalid structured response",
            error_context=self._context(
                "generation",
                phase=phase,
                error_category=category,
                **(
                    conversion_context(exc)
                    if phase == "domain_conversion"
                    else validation_context(exc)
                    if isinstance(exc, ValidationError)
                    else {}
                ),
            ),
        )

    def _request(
        self, operation: str, action: Callable[[], Any], *, embedding_kind: str = "query_embedding"
    ) -> Any:
        if operation in {"generation", "answer generation"}:
            record_provider_call("generation_calls")
        with provider_observation(
            "gemini",
            self._settings.gemini_embedding_model
            if operation == "embedding"
            else self._settings.gemini_generation_model,
            embedding_kind if operation == "embedding" else operation,
        ):
            try:
                response = action()
                record_provider_tokens(getattr(response, "usage_metadata", None))
                return response
            except errors.APIError as exc:
                self._raise_api_error(operation, exc)
            except httpx.TimeoutException as exc:
                raise ProviderError(
                    "Gemini request timed out",
                    error_context=self._context(
                        operation, phase="request", error_category="timeout"
                    ),
                ) from exc
            except httpx.RequestError as exc:
                raise ProviderError(
                    "Gemini connection failed",
                    error_context=self._context(
                        operation, phase="request", error_category="connection_failure"
                    ),
                ) from exc
            except (ValidationError, ValueError, TypeError) as exc:
                raise ProviderError(
                    "Gemini SDK request preparation failed",
                    error_context=self._context(
                        operation, phase="request", error_category="sdk_preparation"
                    ),
                ) from exc
            except Exception as exc:
                raise ModelResponseError(
                    "Gemini request failed",
                    error_context=self._context(
                        operation, phase="request", error_category="internal_failure"
                    ),
                ) from exc

    def generate_text(self, prompt: str) -> str:
        response = self._request(
            "answer generation",
            lambda: self._client.models.generate_content(
                model=self._settings.gemini_generation_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1),
            ),
        )
        try:
            text = response.text.strip()
            if not text:
                raise ValueError("empty response")
            return text
        except Exception as exc:
            raise ModelResponseError(
                "Gemini answer generation failed",
                error_context=self._context(
                    "answer generation", phase="response", error_category="invalid_response"
                ),
            ) from exc

    def embed_query(self, content: str) -> list[float]:
        prepared = f"task: question answering | query: {content}"
        return self._embed_one(prepared)

    def embed_document(self, title: str, content: str) -> list[float]:
        prepared = f"title: {title or 'none'} | text: {content}"
        return self._embed_one(prepared, document=True)

    def _embed_one(self, content: str, *, document: bool = False) -> list[float]:
        """Embed one logical input; Embedding 2 aggregates multi-part inputs."""

        record_provider_call("document_embedding_calls" if document else "query_embedding_calls")
        response = self._request(
            "embedding",
            lambda: self._client.models.embed_content(
                model=self._settings.gemini_embedding_model,
                contents=content,
                config=types.EmbedContentConfig(
                    output_dimensionality=self._settings.embedding_dimensions
                ),
            ),
            embedding_kind="document_embedding" if document else "query_embedding",
        )
        try:
            if len(response.embeddings) != 1:
                raise ValueError("expected exactly one embedding")
            vector = list(response.embeddings[0].values)
            if len(vector) != self._settings.embedding_dimensions:
                raise ValueError("unexpected embedding dimensionality")
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("non-finite embedding")
            return vector
        except Exception as exc:
            raise ModelResponseError(
                "Gemini embedding request failed",
                error_context=self._context(
                    "embedding", phase="response", error_category="invalid_response"
                ),
            ) from exc

    def _raise_api_error(self, operation: str, exc: errors.APIError) -> None:
        category = provider_category(exc.code)
        if exc.code == 400:
            message = str(exc.message).lower()
            if any(
                term in message
                for term in ("too many states", "too much branching", "too complex", "complexity")
            ):
                category = "schema_complexity"
            elif "schema" in message:
                category = "schema_rejected"
        logger.warning(
            "provider_error provider=gemini operation=%s http_status=%s category=%s",
            operation,
            exc.code,
            category,
        )
        message = (
            f"Gemini {operation} is temporarily unavailable"
            if exc.code in TRANSIENT_HTTP_STATUS_CODES
            else f"Gemini {operation} request was rejected; verify API configuration"
        )
        raise ProviderError(
            message,
            error_context=self._context(
                operation,
                phase="request",
                http_status=exc.code,
                error_category=category,
            ),
        ) from exc
