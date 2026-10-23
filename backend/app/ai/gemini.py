"""Small Google GenAI SDK adapter with validated structured outputs."""

import logging
from typing import Any, Protocol, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.errors import (
    TRANSIENT_PROVIDER_STATUSES,
    ConfigurationError,
    ModelResponseError,
    StructuredResponseError,
)
from app.text_to_sql.generation_contract import GenerationDecision
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
        prompt_suffix = (
            "\nReturn the flat GenerationDecision schema: outcome=query with an empty reason; "
            "zero limit and empty where/having mean absent. Every expression has value='' and "
            "value_type=none unless it is a literal. For unsupported, give reason and make "
            "source/where/having empty, limit=0, and all arrays empty. No enclosing plan object."
            if wire_model is GenerationDecision
            else ""
        )
        try:
            response = self._client.models.generate_content(
                model=self._settings.gemini_generation_model,
                contents=prompt + prompt_suffix,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=(
                        _generation_schema(wire_model.model_json_schema())
                        if wire_model is GenerationDecision
                        else _without_additional_properties(wire_model.model_json_schema())
                    ),
                ),
            )
            parsed = wire_model.model_validate_json(response.text)
            if isinstance(parsed, GenerationDecision):
                return response_model.model_validate(parsed.decision())
            return response_model.model_validate(parsed)
        except (ValidationError, ValueError, TypeError) as exc:
            raise StructuredResponseError("Gemini returned an invalid structured response") from exc
        except errors.APIError as exc:
            self._raise_api_error("generation", exc)
        except Exception as exc:
            raise ModelResponseError("Gemini generation request failed") from exc

    def generate_text(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._settings.gemini_generation_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1),
            )
            text = response.text.strip()
            if not text:
                raise ValueError("empty response")
            return text
        except errors.APIError as exc:
            self._raise_api_error("answer generation", exc)
        except Exception as exc:
            raise ModelResponseError("Gemini answer generation failed") from exc

    def embed_query(self, content: str) -> list[float]:
        prepared = f"task: question answering | query: {content}"
        return self._embed_one(prepared)

    def embed_document(self, title: str, content: str) -> list[float]:
        prepared = f"title: {title or 'none'} | text: {content}"
        return self._embed_one(prepared)

    def _embed_one(self, content: str) -> list[float]:
        """Embed one logical input; Embedding 2 aggregates multi-part inputs."""

        try:
            response = self._client.models.embed_content(
                model=self._settings.gemini_embedding_model,
                contents=content,
                config=types.EmbedContentConfig(
                    output_dimensionality=self._settings.embedding_dimensions
                ),
            )
            if len(response.embeddings) != 1:
                raise ValueError("expected exactly one embedding")
            vector = list(response.embeddings[0].values)
            if len(vector) != self._settings.embedding_dimensions:
                raise ValueError("unexpected embedding dimensionality")
            return vector
        except errors.APIError as exc:
            self._raise_api_error("embedding", exc)
        except Exception as exc:
            raise ModelResponseError("Gemini embedding request failed") from exc

    @staticmethod
    def _raise_api_error(operation: str, exc: errors.APIError) -> None:
        category = "request_rejected"
        if exc.code in {401, 403}:
            category = "authentication_or_permission"
        elif exc.code == 429:
            category = "quota_or_rate_limit"
        elif exc.code in TRANSIENT_HTTP_STATUS_CODES:
            category = "transient_unavailable"
        elif exc.code == 400:
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
        if exc.code in TRANSIENT_HTTP_STATUS_CODES:
            raise ModelResponseError(
                f"Gemini {operation} remained unavailable after retry attempts"
            ) from exc
        raise ModelResponseError(
            f"Gemini {operation} request was rejected; verify API configuration"
        ) from exc
