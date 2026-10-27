"""Optional metadata-only Langfuse export; never perform network I/O in a turn."""

import json
import logging
from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from typing import Any, get_args

from app.core.config import Settings
from app.core.errors import ErrorCategory, ErrorPhase

logger = logging.getLogger(__name__)
_client: Any = None
_stages: frozenset[str] = frozenset()
_active: ContextVar[Any] = ContextVar("langfuse_observation", default=None)
_call: ContextVar[tuple[Any, str] | None] = ContextVar("langfuse_provider_call", default=None)
_models = frozenset({"knowledge", "gemini-3.5-flash-lite", "gemini-embedding-2"})
_operations = frozenset(
    {"generation", "answer generation", "query_embedding", "document_embedding"}
)
_strings = {
    "provider": frozenset({"knowledge", "gemini"}),
    "model": _models,
    "route": frozenset({"SQL", "RAG", "HYBRID", "UNSUPPORTED"}),
    "model_id": frozenset({"gemini", "inetcloud-knowledge"}),
    "operation": _operations,
    "status": frozenset({"success", "failure", "unsupported"}),
    "final_status": frozenset({"success", "failure", "unsupported"}),
    "usage_status": frozenset({"measured", "partial", "unknown", "synthetic"}),
    "cost_status": frozenset({"unknown"}),
    "verification_status": frozenset(
        {"unverified", "explanation", "refused", "verified_classification"}
    ),
    "error_category": frozenset(get_args(ErrorCategory)),
    "phase": frozenset(get_args(ErrorPhase)),
}
_counts = frozenset(
    {
        "allowed_tables",
        "approved_edges",
        "result_rows",
        "generation_calls",
        "query_embedding_calls",
        "document_embedding_calls",
        "cached_input_tokens",
        "reasoning_tokens",
    }
)
_flags = frozenset({"sql_validated", "execution_reached", "fallback_used", "synthetic"})


def safe_metadata(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Allow fixed enums and bounded counts only, never content or raw identities."""
    result = {}
    for key, value in facts.items():
        if (
            key in _strings
            and isinstance(value, str)
            and value in _strings[key]
            or key in _counts
            and type(value) is int
            and 0 <= value <= 100_000_000
            or key in _flags
            and type(value) is bool
        ):
            result[key] = value
        elif key == "correlation_id" and isinstance(value, str) and len(value) == 32:
            if all(c in "0123456789abcdef" for c in value):
                result[key] = value
        elif (
            key == "http_status"
            and type(value) is int
            and 100 <= value <= 599
            or key == "origin_stage"
            and isinstance(value, str)
            and value in _stages
        ):
            result[key] = value
    return result


def _mask_spans(*, params: Any) -> Any:
    """SDK export boundary: discard non-allowlisted attributes, including raw I/O."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    scalar = {
        "langfuse.observation.type": {"span", "generation", "embedding"},
        "langfuse.observation.level": {"DEFAULT", "WARNING", "ERROR"},
        "langfuse.observation.model.name": _models,
        "langfuse.observation.status_message": set(get_args(ErrorCategory)),
        "langfuse.internal.as_root": {True},
        "langfuse.internal.is_app_root": {True},
    }
    patches = {}
    prefix = "langfuse.observation.metadata."
    for identifier, span in params.spans.items():
        remove = []
        for key, value in span.attributes.items():
            keep = False
            if key.startswith(prefix):
                name = key.removeprefix(prefix)
                with suppress(ValueError, TypeError):
                    keep = name in safe_metadata({name: json.loads(value)})
            elif key == "langfuse.observation.usage_details":
                with suppress(ValueError, TypeError):
                    usage = json.loads(value)
                    keep = isinstance(usage, dict) and all(
                        k in {"input", "output", "total"}
                        and type(v) is int
                        and 0 <= v <= 10_000_000
                        for k, v in usage.items()
                    )
            elif key in scalar and isinstance(value, (str, bool)):
                keep = value in scalar[key]
            if not keep:
                remove.append(key)
        patches[identifier] = OtelSpanPatch(delete_attributes=remove)
    return MaskOtelSpansResult(span_patches=patches)


def configure(settings: Settings, stages: Collection[str]) -> None:
    """Initialize once at startup, without auth checks or other synchronous requests."""
    global _client, _stages
    _stages = frozenset(stages)
    _client = None
    if not settings.langfuse_enabled:
        return
    if not all(
        (settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_base_url)
    ):
        logger.warning("observability_configuration_missing")
        return
    try:
        from langfuse import Langfuse
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import SpanLimits, TracerProvider

        # SDK logging can include endpoints/keys; application messages stay content-free.
        logging.getLogger("langfuse").setLevel(logging.CRITICAL)
        provider = TracerProvider(
            resource=Resource({"service.name": "shopquery-ai"}),
            span_limits=SpanLimits(max_attributes=64, max_attribute_length=1024),
        )
        _client = Langfuse(
            public_key=settings.langfuse_public_key.get_secret_value(),
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            base_url=str(settings.langfuse_base_url).rstrip("/"),
            tracer_provider=provider,
            timeout=1,
            flush_at=64,
            flush_interval=5,
            mask=lambda *, data: safe_metadata(data) if isinstance(data, Mapping) else None,
            mask_otel_spans=_mask_spans,
            should_export_span=lambda span: (
                span.instrumentation_scope is not None
                and span.instrumentation_scope.name == "langfuse-sdk"
                and span.name in _stages | _operations
            ),
        )
    except Exception:
        logger.warning("observability_initialization_failed")


def shutdown() -> None:
    """Shutdown only with the application, never flush in a request."""
    global _client
    client, _client = _client, None
    if client is not None:
        with suppress(Exception):
            client.shutdown()


def update(**facts: Any) -> None:
    span = _active.get()
    if span is not None:
        with suppress(Exception):
            metadata = safe_metadata(facts)
            span.update(
                metadata=metadata,
                **({"level": "ERROR"} if metadata.get("status") == "failure" else {}),
            )


@contextmanager
def observation(name: str, *, trace_id: str | None = None, **options: Any) -> Iterator[Any]:
    client = _client
    manager = span = None
    if client is not None:
        try:
            manager = client.start_as_current_observation(
                name=name,
                **({"trace_context": {"trace_id": trace_id}} if trace_id else {}),
                **options,
            )
            span = manager.__enter__()
        except Exception:
            manager = None
    token = _active.set(span)
    try:
        yield span
    except BaseException as exc:
        context = getattr(exc, "error_context", None)
        category = getattr(context, "error_category", None) or "internal_failure"
        if span is not None:
            with suppress(Exception):
                span.update(
                    level="ERROR",
                    status_message=category
                    if category in _strings["error_category"]
                    else "internal_failure",
                    metadata=safe_metadata(
                        {
                            "status": "failure",
                            "error_category": category,
                            "http_status": getattr(context, "http_status", None),
                            "phase": getattr(context, "phase", None),
                        }
                    ),
                )
        raise
    finally:
        _active.reset(token)
        if manager is not None:
            # Do not let OTEL auto-record exception messages, stacktraces or SQL.
            with suppress(Exception):
                manager.__exit__(None, None, None)


@contextmanager
def provider_observation(provider: str, model: str, operation: str) -> Iterator[None]:
    with observation(
        operation,
        as_type="embedding" if "embedding" in operation else "generation",
        model=model if model in _models else None,
        metadata=safe_metadata(
            {
                "provider": provider,
                "model": model,
                "operation": operation,
                "usage_status": "unknown",
                "cost_status": "unknown",
            }
        ),
    ) as span:
        token = _call.set((span, provider))
        try:
            yield
        finally:
            _call.reset(token)


def record_usage(usage: object) -> None:
    """Preserve SDK totals; cached/reasoning counts are descriptive, never added twice."""
    call = _call.get()
    if call is None or call[0] is None or usage is None:
        return
    span, provider = call
    fields = (
        {"input": "input_tokens", "output": "output_tokens", "total": "total_tokens"}
        if provider == "knowledge"
        else {
            "input": "prompt_token_count",
            "output": "candidates_token_count",
            "total": "total_token_count",
        }
    )
    counts = {}
    for key, field in fields.items():
        value = usage.get(field) if isinstance(usage, dict) else getattr(usage, field, None)
        if type(value) is int and 0 <= value <= 10_000_000:
            counts[key] = value
    details = usage.get("input_token_details", {}) if isinstance(usage, dict) else {}
    output_details = usage.get("output_token_details", {}) if isinstance(usage, dict) else {}
    cached = details.get("cache_read") if isinstance(details, dict) else None
    reasoning = output_details.get("reasoning") if isinstance(output_details, dict) else None
    if provider == "gemini":
        cached = getattr(usage, "cached_content_token_count", None)
        reasoning = getattr(usage, "thoughts_token_count", None)
    metadata = safe_metadata(
        {
            "usage_status": "measured" if len(counts) == 3 else "partial" if counts else "unknown",
            "cached_input_tokens": cached,
            "reasoning_tokens": reasoning,
        }
    )
    with suppress(Exception):
        span.update(usage_details=counts or None, metadata=metadata)
