"""Vietnamese month boundaries on PostgreSQL, including both provider regressions."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Column, DateTime, Engine, Integer, MetaData, Table, create_engine, text

from app.core.config import get_settings
from app.core.errors import SqlExecutionError
from app.database.session import get_setup_engine
from app.database.setup import create_schema
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.validator import SqlValidator

pytestmark = pytest.mark.integration

MONTHS = [
    ("2025-09-01", "2025-10-01"),
    ("2025-12-01", "2026-01-01"),
    ("2024-02-01", "2024-03-01"),
]
BOUNDARY_FORMS = {
    "explicit_offset": "TIMESTAMPTZ '{date} 00:00:00+07:00'",
    "local_timestamp": "TIMESTAMP '{date} 00:00:00' AT TIME ZONE 'Asia/Ho_Chi_Minh'",
    "knowledge_regression": "CAST('{date}' AS TIMESTAMPTZ) AT TIME ZONE 'Asia/Ho_Chi_Minh'",
    "gemini_regression": "CAST('{date} 00:00:00+07' AS TIMESTAMP)",
    "date_literal": "DATE '{date}'",
}
CalendarExecutor = tuple[SqlExecutor, SqlValidator, Engine, str]


@pytest.fixture(scope="module")
def calendar_table() -> Iterator[Table]:
    setup = get_setup_engine()
    assert setup.url.database != "shopquery", "Calendar fixtures require an isolated test database"
    create_schema(setup)
    metadata = MetaData()
    table = Table(
        f"calendar_events_{uuid4().hex}",
        metadata,
        Column("event_id", Integer, primary_key=True),
        Column("occurred_at", DateTime(timezone=True), nullable=False),
        schema="uploaded_data",
    )
    metadata.create_all(setup)
    try:
        rows = []
        for month_index, (start_date, end_date) in enumerate(MONTHS):
            start = datetime.fromisoformat(f"{start_date}T00:00:00+07:00")
            end = datetime.fromisoformat(f"{end_date}T00:00:00+07:00")
            moments = [
                start - timedelta(microseconds=1),
                start,
                start + timedelta(hours=6, minutes=59, seconds=59, microseconds=999999),
                end - timedelta(microseconds=1),
                end,
                end + timedelta(hours=7, minutes=10, seconds=7),
            ]
            rows.extend(
                {"event_id": month_index * 10 + index, "occurred_at": moment}
                for index, moment in enumerate(moments, start=1)
            )
        with setup.begin() as connection:
            connection.execute(table.insert(), rows)
        yield table
    finally:
        metadata.drop_all(setup)


@pytest.fixture(params=["UTC", "America/Los_Angeles"])
def calendar_executor(
    request: pytest.FixtureRequest, calendar_table: Table
) -> Iterator[CalendarExecutor]:
    engine = create_engine(
        get_settings().database_readonly_url,
        connect_args={"options": f"-c timezone={request.param}"},
        pool_size=1,
        max_overflow=0,
    )
    validator = SqlValidator(
        table_columns={calendar_table.name: {"event_id", "occurred_at"}},
        allowed_schemas={calendar_table.name: "uploaded_data"},
    )
    try:
        yield SqlExecutor(engine, timeout_ms=5_000, max_rows=20), validator, engine, request.param
    finally:
        engine.dispose()


@pytest.mark.parametrize("month_index", range(len(MONTHS)))
@pytest.mark.parametrize("boundary_form", BOUNDARY_FORMS)
def test_month_filter_includes_start_and_excludes_end_in_vietnam(
    calendar_table: Table,
    calendar_executor: CalendarExecutor,
    month_index: int,
    boundary_form: str,
) -> None:
    executor, validator, engine, original_timezone = calendar_executor
    start, end = MONTHS[month_index]
    form = BOUNDARY_FORMS[boundary_form]
    sql = (
        f"SELECT event_id FROM uploaded_data.{calendar_table.name} "
        f"WHERE occurred_at >= {form.format(date=start)} "
        f"AND occurred_at < {form.format(date=end)} ORDER BY event_id"
    )

    rows = executor.execute(validator.validate(sql))

    assert rows == [{"event_id": month_index * 10 + index} for index in (2, 3, 4)]
    with engine.connect() as connection:
        assert connection.scalar(text("SHOW TimeZone")) == original_timezone


@pytest.mark.parametrize("month_index", range(len(MONTHS)))
def test_month_grouping_uses_vietnamese_midnight(
    calendar_table: Table, calendar_executor: CalendarExecutor, month_index: int
) -> None:
    executor, validator, _, _ = calendar_executor
    start, end = MONTHS[month_index]
    sql = (
        "SELECT DATE_TRUNC('month', occurred_at) AS sales_month, COUNT(*) AS n "
        f"FROM uploaded_data.{calendar_table.name} "
        f"WHERE occurred_at >= TIMESTAMPTZ '{start} 00:00:00+07' "
        f"AND occurred_at < TIMESTAMPTZ '{end} 00:00:00+07' "
        "GROUP BY DATE_TRUNC('month', occurred_at)"
    )

    assert executor.execute(validator.validate(sql)) == [
        {"sales_month": f"{start}T00:00:00+07:00", "n": 3}
    ]


@pytest.mark.parametrize("failure", ["query", "row_limit"])
def test_timezone_does_not_leak_to_pooled_connection_after_error(
    calendar_table: Table, calendar_executor: CalendarExecutor, failure: str
) -> None:
    executor, validator, engine, original_timezone = calendar_executor
    with engine.connect() as connection:
        original_pid = connection.scalar(text("SELECT pg_backend_pid()"))
    expression = "1 / 0" if failure == "query" else "event_id"
    if failure == "row_limit":
        executor = SqlExecutor(engine, timeout_ms=5_000, max_rows=1)
    sql = f"SELECT {expression} FROM uploaded_data.{calendar_table.name}"

    with pytest.raises(SqlExecutionError):
        executor.execute(validator.validate(sql))

    with engine.connect() as connection:
        assert connection.scalar(text("SHOW TimeZone")) == original_timezone
        assert connection.scalar(text("SELECT pg_backend_pid()")) == original_pid
