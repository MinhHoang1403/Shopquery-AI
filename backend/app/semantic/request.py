"""Backend identity and catalog binding for one authenticated API request."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Literal
from uuid import UUID

from app.core.errors import ErrorContext, ModelResponseError
from app.datasets.context import DatasetSqlContext
from app.semantic.task import RequestContext
from app.text_to_sql.schema_context import BUSINESS_TIME_ZONE


def catalog_revision(context: DatasetSqlContext) -> str:
    """Bind all issued metadata, not just the number or spelling of columns."""

    def encode(value):
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, UUID):
            return str(value)
        raise TypeError("Unsupported catalog metadata")

    return sha256(
        json.dumps(asdict(context), sort_keys=True, default=encode, ensure_ascii=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class RequestIdentity:
    owner_user_id: UUID | None
    conversation_id: UUID | None
    dataset_id: int | None
    question: str
    reference_date: str
    principal: Literal["authenticated", "guest"] = "authenticated"
    guest_request_id: UUID | None = None


_identity: ContextVar[RequestIdentity | None] = ContextVar(
    "semantic_request_identity", default=None
)
_catalog: ContextVar[str | None] = ContextVar("semantic_request_catalog", default=None)
_capabilities: ContextVar[tuple[str, ...] | None] = ContextVar(
    "semantic_request_capabilities", default=None
)


def request_active() -> bool:
    return _identity.get() is not None


@contextmanager
def semantic_request(identity: RequestIdentity) -> Iterator[None]:
    token = _identity.set(identity)
    catalog_token = _catalog.set(None)
    capabilities_token = _capabilities.set(None)
    try:
        yield
    finally:
        _capabilities.reset(capabilities_token)
        _catalog.reset(catalog_token)
        _identity.reset(token)


def bind_request(
    context: DatasetSqlContext, capabilities: tuple[str, ...]
) -> RequestContext | None:
    identity = _identity.get()
    if identity is None:
        return None
    if identity.principal == "guest" and (
        context.owner_user_id is not None
        or context.dataset_id != 0
        or any(schema != "pg_temp" for schema in context.allowed_schemas.values())
    ):
        raise ModelResponseError(
            "Guest semantic requests cannot use persistent catalogs",
            error_context=ErrorContext(
                phase="verification",
                error_category="insufficient_evidence",
                reason_code="planning_scope_violation",
            ),
        )
    if context.dataset_id != identity.dataset_id or (
        context.dataset_id is not None and context.owner_user_id != identity.owner_user_id
    ):
        raise ModelResponseError(
            "Request catalog scope is inconsistent",
            error_context=ErrorContext(
                phase="verification",
                error_category="insufficient_evidence",
                reason_code="planning_scope_violation",
            ),
        )
    revision = catalog_revision(context)
    issued = _catalog.get()
    if issued is not None and issued != revision:
        raise ModelResponseError(
            "Catalog changed during semantic planning",
            error_context=ErrorContext(
                phase="verification",
                error_category="insufficient_evidence",
                reason_code="planning_scope_violation",
            ),
        )
    _catalog.set(revision)
    issued_capabilities = _capabilities.get()
    if issued_capabilities is None:
        _capabilities.set(capabilities)
    else:
        capabilities = tuple(cap for cap in capabilities if cap in issued_capabilities)
    return RequestContext(
        **asdict(identity),
        catalog_revision=revision,
        time_zone=BUSINESS_TIME_ZONE,
        authorized_capabilities=capabilities,
    )
