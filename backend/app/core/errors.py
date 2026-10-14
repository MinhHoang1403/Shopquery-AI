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
