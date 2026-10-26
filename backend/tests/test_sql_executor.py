"""Transaction-local calendar configuration and rollback guarantees."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.core.errors import SqlExecutionError
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.validator import ValidatedSql


def executor_connection() -> tuple[SqlExecutor, MagicMock]:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    return SqlExecutor(engine, timeout_ms=5_000, max_rows=1), connection


def test_executor_applies_vietnamese_timezone_only_within_readonly_transaction() -> None:
    executor, connection = executor_connection()
    connection.execute.return_value.mappings.return_value.fetchmany.return_value = [{"n": 1}]
    validated = ValidatedSql("SELECT COUNT(*) AS n FROM orders", frozenset({"orders"}))

    assert executor.execute(validated) == [{"n": 1}]

    calls = connection.execute.call_args_list
    assert str(calls[0].args[0]) == "SET TRANSACTION READ ONLY"
    assert str(calls[1].args[0]) == "SELECT set_config('statement_timeout', :timeout, true)"
    assert calls[1].args[1] == {"timeout": "5000"}
    assert str(calls[2].args[0]) == "SELECT set_config('TimeZone', :timezone, true)"
    assert calls[2].args[1] == {"timezone": "Asia/Ho_Chi_Minh"}
    assert str(calls[3].args[0]) == validated.statement
    connection.begin.return_value.rollback.assert_called_once()


def test_driver_sqlstate_is_preserved_without_sensitive_query_or_driver_message():
    from types import SimpleNamespace

    executor, connection = executor_connection()
    connection.execute.side_effect = DBAPIError(
        "PRIVATE SQL",
        {"secret": "PRIVATE"},
        SimpleNamespace(sqlstate="42703", message="PRIVATE driver"),
    )
    with pytest.raises(SqlExecutionError) as caught:
        executor.execute(ValidatedSql("SELECT n FROM orders", frozenset({"orders"})))
    assert caught.value.error_context.sqlstate == "42703"
    assert caught.value.error_context.validation_branch == "database_error"
    assert "PRIVATE" not in str(caught.value) + caught.value.error_context.model_dump_json()


@pytest.mark.parametrize("failure", ["query", "row_limit", "timezone"])
def test_executor_rolls_back_transaction_settings_on_failure(failure: str) -> None:
    executor, connection = executor_connection()
    result = MagicMock()
    result.mappings.return_value.fetchmany.return_value = [{"n": 1}, {"n": 2}]

    def execute(statement: object, *args: object) -> MagicMock:
        sql = str(statement)
        if failure == "timezone" and "set_config('TimeZone'" in sql:
            raise SQLAlchemyError("timezone configuration failed")
        if failure == "query" and sql.startswith("SELECT n"):
            raise SQLAlchemyError("query failed")
        return result

    connection.execute.side_effect = execute
    with pytest.raises(SqlExecutionError):
        executor.execute(ValidatedSql("SELECT n FROM orders", frozenset({"orders"})))

    connection.begin.return_value.rollback.assert_called_once()
