"""Bounded request diagnostics with no question, SQL, result values or identities."""

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter
from typing import Any, ParamSpec, TypeVar
from uuid import uuid4

logger = logging.getLogger(__name__)
P = ParamSpec("P")
T = TypeVar("T")
STAGES = frozenset(
    {
        "workspace_binding",
        "schema_metadata",
        "relationship_discovery",
        "relationship_approval",
        "router_unsupported",
        "generator_unsupported",
        "structured_output_invalid",
        "sql_parse_error",
        "column_resolution",
        "join_graph",
        "join_relationship",
        "join_key",
        "join_aggregate",
        "join_grain",
        "execution_guard",
        "sql_execution",
        "answer_grounding",
        "frontend_rendering",
        "document_retrieval",
        "request",
    }
)
REASONS = STAGES | frozenset(
    {
        "ok",
        "failed",
        "unsupported",
        "filter",
        "projection_expression",
        "multiple_arguments",
        "count_star_alias",
        "argument_expression",
        "dimension_column",
        "count_column_alias",
        "unsupported_function",
        "non_numeric_fact",
        "identifier_measure",
        "count_semantics",
    }
)


@dataclass
class DiagnosticTrace:
    correlation_id: str
    facts: dict[str, Any] = field(
        default_factory=lambda: {
            "model": None,
            "allowed_tables": 0,
            "approved_edges": 0,
            "route": None,
            "sql_validated": False,
            "execution_reached": False,
            "result_rows": 0,
            "final_status": None,
        }
    )
    events: list[dict[str, Any]] = field(default_factory=list)


_trace: ContextVar[DiagnosticTrace | None] = ContextVar("diagnostic_trace", default=None)


def current_correlation_id() -> str | None:
    trace = _trace.get()
    return trace.correlation_id if trace else None


def record_facts(**facts: Any) -> None:
    trace = _trace.get()
    if trace is None:
        return
    for key, value in facts.items():
        if key == "model" and isinstance(value, str) and value in {"gemini", "inetcloud-knowledge"}:
            trace.facts[key] = value
        elif (
            key == "route"
            and isinstance(value, str)
            and value in {"SQL", "RAG", "HYBRID", "UNSUPPORTED"}
        ):
            trace.facts[key] = str(value)
        elif key in {"allowed_tables", "approved_edges", "result_rows"} and type(value) is int:
            trace.facts[key] = max(0, value)
        elif (
            key in {"sql_validated", "execution_reached"}
            and type(value) is bool
            or key == "final_status"
            and isinstance(value, str)
            and value in {"failure", "unsupported", "success"}
        ):
            trace.facts[key] = value


def publish_events(events: list[dict[str, Any]]) -> None:
    for event in events[:64]:
        with suppress(Exception):
            logger.info("pipeline_diagnostic %s", json.dumps(event, sort_keys=True))


def relay_events(events: list[dict[str, Any]]) -> None:
    publish_events(events)
    if events:
        record_facts(**events[-1])


def record_refusal(stage: str) -> None:
    _event(stage, "unsupported", "unsupported", 0)


def _event(stage: str, status: str, reason: str, duration: float) -> None:
    trace = _trace.get()
    if trace is None:
        return
    event = {
        "correlation_id": trace.correlation_id,
        "stage": stage if stage in STAGES else "request",
        "status": status,
        "reason": reason if reason in REASONS else "failed",
        "duration_ms": round(max(0, duration) * 1000, 3),
        **trace.facts,
    }
    if len(trace.events) < 64:
        trace.events.append(event)
    publish_events([event])


@contextmanager
def diagnostic_request(correlation_id: str | None = None) -> Iterator[DiagnosticTrace]:
    existing = _trace.get()
    if existing is not None:
        yield existing
        return
    identifier = (
        correlation_id
        if correlation_id
        and len(correlation_id) == 32
        and all(c in "0123456789abcdef" for c in correlation_id)
        else uuid4().hex
    )
    trace = DiagnosticTrace(identifier)
    token = _trace.set(trace)
    start = perf_counter()
    try:
        yield trace
    except BaseException:
        _event("request", "failure", "failed", perf_counter() - start)
        raise
    else:
        unsupported = trace.facts["route"] == "UNSUPPORTED"
        status = trace.facts["final_status"] or ("unsupported" if unsupported else "success")
        _event(
            "request",
            status,
            "failed" if status == "failure" else "unsupported" if unsupported else "ok",
            perf_counter() - start,
        )
    finally:
        _trace.reset(token)


@contextmanager
def diagnostic_stage(stage: str) -> Iterator[None]:
    start = perf_counter()
    try:
        yield
    except BaseException as exc:
        code = getattr(exc, "code", None)
        failed_stage = code if isinstance(code, str) and code in STAGES else stage
        if getattr(exc, "structured_output_invalid", False):
            failed_stage = "structured_output_invalid"
        reason = getattr(exc, "aggregate_reason", None) or failed_stage
        _event(failed_stage, "failure", reason, perf_counter() - start)
        raise
    else:
        _event(stage, "success", "ok", perf_counter() - start)


def diagnosed(function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        with diagnostic_request():
            return function(*args, **kwargs)

    return wrapper
