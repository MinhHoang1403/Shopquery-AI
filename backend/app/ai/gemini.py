"""Small Google GenAI SDK adapter with validated structured outputs."""

import logging
from typing import Protocol, TypeVar

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

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)
TRANSIENT_HTTP_STATUS_CODES = list(TRANSIENT_PROVIDER_STATUSES)
logger = logging.getLogger(__name__)


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
        try:
            response = self._client.models.generate_content(
                model=self._settings.gemini_generation_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=response_model,
                ),
            )
            return response_model.model_validate_json(response.text)
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
            if "schema" in message:
                category = "schema_rejected"
                if any(
                    term in message
                    for term in (
                        "too many states", "too much branching", "too complex", "complexity"
                    )
                ):
                    category = "schema_complexity"
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
