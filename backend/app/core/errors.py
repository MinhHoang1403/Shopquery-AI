"""Domain errors safe to translate into API responses."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

TRANSIENT_PROVIDER_STATUSES = (408, 429, 500, 502, 503, 504)

ErrorCategory = Literal[
    "request_rejected",
    "schema_rejected",
    "schema_complexity",
    "authentication_or_permission",
    "timeout",
    "quota_or_rate_limit",
    "transient_unavailable",
    "connection_failure",
    "sdk_preparation",
    "invalid_json",
    "wire_validation",
    "contract_conversion",
    "model_refusal",
    "invalid_response",
    "sql_validation",
    "sql_execution",
    "insufficient_evidence",
    "provider_disabled",
    "configuration",
    "internal_failure",
]
ErrorPhase = Literal[
    "schema_preparation",
    "request",
    "json_decode",
    "wire_validation",
    "domain_conversion",
    "response",
    "compilation",
    "execution",
    "verification",
]

VerificationReason = Literal[
    "planning_scope_violation",
    "policy_not_retrieved",
    "policy_parse_failed",
    "policy_document_scope_invalid",
    "policy_document_hash_mismatch",
    "policy_multiple_candidates",
    "policy_ambiguous",
    "policy_unsupported_qualifier",
    "policy_not_verified",
    "policy_identity_unbound",
    "policy_metric_unbound",
    "policy_aggregate_mismatch",
    "policy_source_table_mismatch",
    "policy_grouping_mismatch",
    "policy_unit_mismatch",
    "policy_sql_scope_incomplete",
    "policy_join_path_ambiguous",
    "classification_identity_mismatch",
    "classification_missing_entities",
    "classification_duplicate_entities",
    "classification_status_mismatch",
    "classification_policy_reference_invalid",
    "classification_metric_invalid",
    "citation_missing",
    "citation_chunk_not_retrieved",
    "citation_rule_source_mismatch",
    "citation_quote_mismatch",
    "answer_draft_inconsistent",
]


class ErrorContext(BaseModel):
    """Only bounded, non-content metadata may cross provider/API/log boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["knowledge", "gemini"] | None = None
    operation: Literal["generation", "answer generation", "embedding"] | None = None
    origin_stage: str | None = Field(default=None, max_length=64, pattern=r"^[a-z_]+$")
    phase: ErrorPhase | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    error_category: ErrorCategory | None = None
    attempt: int | None = Field(default=None, ge=1, le=10)
    correlation_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    validation_location: list[str | int] = Field(default_factory=list, max_length=12)
    validation_type: str | None = None
    attempted_route: Literal["SQL", "RAG", "HYBRID", "UNSUPPORTED"] | None = None
    reason_code: VerificationReason | Literal["model_unsupported", "catalog_missing"] | None = None
    model_id: Literal["inetcloud-knowledge", "gemini"] | None = None
    response_outcome: Literal["query", "unsupported"] | None = None
    catalog_table_count: int | None = Field(default=None, ge=0, le=100000)
    catalog_column_count: int | None = Field(default=None, ge=0, le=100000)
    approved_relationship_count: int | None = Field(default=None, ge=0, le=100000)
    model_reason_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    candidate_count: int | None = Field(default=None, ge=0, le=1000000)
    verified_policy_count: int | None = Field(default=None, ge=0, le=1000000)
    retrieved_chunk_count: int | None = Field(default=None, ge=0, le=1000000)
    sql_row_count: int | None = Field(default=None, ge=0, le=1000000)

    @field_validator("validation_location")
    @classmethod
    def safe_location(cls, value: list[str | int]) -> list[str | int]:
        fields = {
            "plan",
            "source",
            "fields",
            "expressions",
            "filters",
            "group_by",
            "sort",
            "limit",
            "relationships",
            "where",
            "having",
            "outcome",
            "reason",
            "reference",
            "alias",
            "operation",
            "arguments",
            "value",
            "value_type",
            "operator",
            "values",
            "field",
            "direction",
            "nulls",
            "unsupported_reason",
            "route",
            "answer",
            "used_chunk_ids",
            "decisions",
            "language",
        }
        return [
            min(max(item, 0), 1000) if type(item) is int else item if item in fields else "<field>"
            for item in value
        ]

    @field_validator("validation_type")
    @classmethod
    def safe_validation_type(cls, value: str | None) -> str | None:
        allowed = {
            "missing",
            "extra_forbidden",
            "literal_error",
            "value_error",
            "json_invalid",
            "string_type",
            "int_type",
            "int_parsing",
            "list_type",
            "dict_type",
            "bool_type",
            "model_type",
            "model_attributes_type",
            "too_short",
            "too_long",
            "enum",
            "greater_than_equal",
            "less_than_equal",
            "string_too_long",
            "string_too_short",
        }
        return value if value is None or value in allowed else "validation_error"


def validation_context(exc: ValidationError) -> dict:
    details = exc.errors(include_input=False, include_context=False, include_url=False)[0]
    clean = ErrorContext(
        validation_location=list(details["loc"])[:12], validation_type=details["type"]
    )
    return clean.model_dump(include={"validation_location", "validation_type"})


def provider_category(status: int) -> ErrorCategory:
    if status in {401, 403}:
        return "authentication_or_permission"
    if status == 408:
        return "timeout"
    if status == 429:
        return "quota_or_rate_limit"
    if status in {500, 502, 503, 504}:
        return "transient_unavailable"
    return "request_rejected"


def error_message(context: ErrorContext) -> str:
    messages = {
        "transient_unavailable": (
            "Nhà cung cấp AI tạm thời không khả dụng. Dữ liệu của bạn vẫn được giữ."
        ),
        "timeout": "Yêu cầu tới nhà cung cấp AI đã hết thời gian chờ.",
        "connection_failure": "Không thể kết nối nhà cung cấp AI.",
        "quota_or_rate_limit": "Nhà cung cấp AI đang giới hạn yêu cầu hoặc hạn mức sử dụng.",
        "authentication_or_permission": (
            "Nhà cung cấp AI từ chối quyền truy cập; cần kiểm tra cấu hình."
        ),
        "request_rejected": "Nhà cung cấp AI từ chối yêu cầu.",
        "schema_rejected": "Nhà cung cấp AI từ chối cấu trúc yêu cầu.",
        "schema_complexity": "Nhà cung cấp AI từ chối cấu trúc yêu cầu quá phức tạp.",
        "sdk_preparation": "Không thể chuẩn bị yêu cầu AI; cần kiểm tra cấu hình SDK.",
        "invalid_json": "AI trả về cấu trúc không hợp lệ; chưa thực thi truy vấn.",
        "wire_validation": "AI trả về cấu trúc không hợp lệ; chưa thực thi truy vấn.",
        "contract_conversion": "Không thể chuyển cấu trúc AI thành truy vấn hợp lệ.",
        "model_refusal": "Nhà cung cấp AI từ chối tạo câu trả lời cho yêu cầu này.",
        "sql_validation": "Truy vấn nằm ngoài khả năng SQL an toàn hiện tại.",
        "sql_execution": "Không thể thực thi truy vấn dữ liệu.",
        "insufficient_evidence": "Chưa đủ bằng chứng đã xác minh để kết luận chính xác.",
        "provider_disabled": "Quản trị viên chưa cho phép gửi dữ liệu tới AI providers.",
        "configuration": "Chức năng AI chưa được cấu hình đầy đủ.",
    }
    return messages.get(context.error_category, "Không thể hoàn tất yêu cầu này.")


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

    def __init__(self, message: str, *, error_context: ErrorContext | None = None) -> None:
        super().__init__(message)
        self.error_context = error_context or ErrorContext()


class ConfigurationError(ShopQueryError):
    """Raised when required runtime configuration is unavailable."""


class ModelResponseError(ShopQueryError):
    """Raised when a model response cannot be validated."""


class StructuredResponseError(ModelResponseError):
    """A response failed the requested schema, not a transport or SQL check."""

    structured_output_invalid = True


class ProviderError(ModelResponseError):
    """Generation failure classified before applying the fallback policy."""

    def __init__(
        self,
        message: str,
        *,
        fallback_allowed: bool = False,
        error_context: ErrorContext | None = None,
    ) -> None:
        super().__init__(message, error_context=error_context)
        self.fallback_allowed = fallback_allowed


class ChatTurnError(ShopQueryError):
    """Preserve attribution when no final model answer could be produced."""

    def __init__(
        self,
        cause: ShopQueryError,
        requested_model: str,
        *,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
        fallback_error_context: ErrorContext | None = None,
    ) -> None:
        super().__init__(str(cause), error_context=cause.error_context)
        self.requested_model = requested_model
        self.fallback_used = fallback_used
        self.fallback_reason = fallback_reason or (
            "primary_provider_unavailable" if fallback_used else None
        )
        self.fallback_error_context = fallback_error_context


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
        error_context: ErrorContext | None = None,
        grain_reason: Literal[
            "fact_source",
            "dimension_measure",
            "subtotal_group",
            "dimension_group_key",
            "multiple_fact_measures",
        ]
        | None = None,
    ) -> None:
        super().__init__(message, error_context=error_context)
        self.grain_reason = grain_reason
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
