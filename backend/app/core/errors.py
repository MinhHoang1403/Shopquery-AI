"""Domain errors safe to translate into API responses."""

from typing import Literal

TRANSIENT_PROVIDER_STATUSES = (408, 429, 500, 502, 503, 504)

JoinAggregateReason = Literal[
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
    "count_wrong_argument_semantics",
    "count_projection_alias_ambiguous",
    "count_order_unprojected",
    "count_order_non_equivalent",
    "count_having_unsupported",
    "count_clause_unsupported",
    "count_group_reference",
]


class ShopQueryError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(ShopQueryError):
    """Raised when required runtime configuration is unavailable."""


class ModelResponseError(ShopQueryError):
    """Raised when a model response cannot be validated."""


class StructuredResponseError(ModelResponseError):
    """A response failed the requested schema, not a transport or SQL check."""

    structured_output_invalid = True


class ProviderError(ModelResponseError):
    """Generation failure classified before applying the fallback policy."""

    def __init__(self, message: str, *, fallback_allowed: bool = False) -> None:
        super().__init__(message)
        self.fallback_allowed = fallback_allowed


class ChatTurnError(ShopQueryError):
    """Preserve attribution when no final model answer could be produced."""

    def __init__(
        self, cause: ShopQueryError, requested_model: str, *, fallback_used: bool = False
    ) -> None:
        super().__init__(str(cause))
        self.requested_model = requested_model
        self.fallback_used = fallback_used


class SqlValidationError(ShopQueryError):
    """Raised when generated SQL is outside the supported safe subset."""


class SqlExecutionError(ShopQueryError):
    """Raised when an approved query cannot be executed safely."""


class SqlUnsupportedError(SqlValidationError):
    """An unsupported relationship/grain must not become a partial numeric answer."""

    def __init__(
        self,
        message: str,
        *,
        reason: Literal["unknown", "relationship", "calculation"] = "unknown",
        code: Literal[
            "join_direction",
            "join_key",
            "join_aggregate",
            "join_relationship",
            "join_graph",
            "join_grain",
            "generator_unsupported",
        ]
        | None = None,
        aggregate_reason: JoinAggregateReason | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.code = code
        self.aggregate_reason = aggregate_reason


class RetrievalError(ShopQueryError):
    """Raised when document retrieval cannot be completed."""


class ResourceNotFoundError(ShopQueryError):
    """Raised when a requested conversation or dataset does not exist."""


class ResourceConflictError(ShopQueryError):
    """Raised when a unique application resource already exists."""


class UploadValidationError(ShopQueryError):
    """Raised when an uploaded tabular file is unsafe or invalid."""
