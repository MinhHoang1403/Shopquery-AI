"""Domain errors safe to translate into API responses."""


class ShopQueryError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(ShopQueryError):
    """Raised when required runtime configuration is unavailable."""


class ModelResponseError(ShopQueryError):
    """Raised when a model response cannot be validated."""


class SqlValidationError(ShopQueryError):
    """Raised when generated SQL is outside the supported safe subset."""


class SqlExecutionError(ShopQueryError):
    """Raised when an approved query cannot be executed safely."""


class RetrievalError(ShopQueryError):
    """Raised when document retrieval cannot be completed."""


class ResourceNotFoundError(ShopQueryError):
    """Raised when a requested conversation or dataset does not exist."""


class ResourceConflictError(ShopQueryError):
    """Raised when a unique application resource already exists."""


class UploadValidationError(ShopQueryError):
    """Raised when an uploaded tabular file is unsafe or invalid."""
