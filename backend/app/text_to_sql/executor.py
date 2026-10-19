"""Read-only SQL execution with transaction timeout and bounded results."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import SqlExecutionError
from app.text_to_sql.schema_context import BUSINESS_TIME_ZONE
from app.text_to_sql.validator import ValidatedSql


class SqlExecutor:
    def __init__(self, engine: Engine, timeout_ms: int, max_rows: int) -> None:
        self._engine = engine
        self._timeout_ms = timeout_ms
        self._max_rows = max_rows

    def execute(self, validated: ValidatedSql) -> list[dict[str, Any]]:
        try:
            with self._engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    connection.execute(
                        text("SELECT set_config('statement_timeout', :timeout, true)"),
                        {"timeout": str(self._timeout_ms)},
                    )
                    connection.execute(
                        text("SELECT set_config('TimeZone', :timezone, true)"),
                        {"timezone": BUSINESS_TIME_ZONE},
                    )
                    result = connection.execute(text(validated.statement))
                    raw_rows = result.mappings().fetchmany(self._max_rows + 1)
                    if len(raw_rows) > self._max_rows:
                        raise SqlExecutionError(
                            f"Query exceeded the {self._max_rows}-row response limit"
                        )
                    return [
                        {key: _json_safe(value) for key, value in row.items()}
                        for row in raw_rows
                    ]
                finally:
                    transaction.rollback()
        except SqlExecutionError:
            raise
        except SQLAlchemyError as exc:
            raise SqlExecutionError("The validated query could not be executed") from exc


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
