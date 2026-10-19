"""Correctness checks only against an explicitly isolated PostgreSQL database."""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.conversations.repository import ConversationRepository
from app.core.config import get_settings
from app.database.guest_access import configure_guest_access
from app.database.session import get_readonly_engine, get_setup_engine
from app.database.test_safety import require_test_database
from app.datasets.context import build_dataset_sql_context
from app.datasets.repository import DatasetRepository
from app.guest.pipeline import GuestSqlDatabase
from app.guest.worker import parse_guest_file
from app.main import app
from app.routing.router import RouteLabel
from app.routing.service import ChatResult
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.validator import SqlValidator
from tests.auth_helpers import TEST_OWNER, TestClient
from tests.test_dataset_parser import parse, xlsx_bytes

pytestmark = pytest.mark.integration

TEMPORAL_ROWS = [
    ["A", "2026-09-30", "2026-09-30T23:59:59", "2026-09-30T23:59:59.999999+07:00", 10],
    ["B", "2026-10-01", "2026-10-01T00:00:00", "2026-10-01T00:00:00+07:00", 20],
    ["C", "2026-10-01", "2026-10-01T00:00:00", "2026-09-30T17:00:00Z", 30],
    ["D", "2027-01-01", "2027-01-01T00:00:00", "2026-12-31T17:00:00Z", 40],
    ["E", "2026-12-31", "2026-12-31T23:59:59", "2026-12-31T23:59:59+07:00", 50],
    ["F", "2027-01-01", "2027-01-01T11:00:00", "2027-01-01T00:00:00-04:00", 60],
]


def temporal_file(format: str) -> bytes:
    headers = ["Mã", "Ngày", "Local", "Instant", "Amount"]
    if format == "csv":
        return (
            ",".join(headers) + "\n" + "\n".join(",".join(map(str, row)) for row in TEMPORAL_ROWS)
        ).encode()
    return xlsx_bytes(
        [
            headers,
            *[
                [row[0], date.fromisoformat(row[1]), datetime.fromisoformat(row[2]), row[3], row[4]]
                for row in TEMPORAL_ROWS
            ],
        ]
    )


@pytest.mark.parametrize("writer_timezone", ["UTC", "Asia/Ho_Chi_Minh"])
@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_new_import_preserves_instants_dates_and_calendar_months(
    writer_timezone: str,
    format: str,
) -> None:
    url = get_settings().database_setup_url
    require_test_database(url)
    engine = create_engine(url, connect_args={"options": f"-c timezone={writer_timezone}"})
    repository = DatasetRepository(engine, get_readonly_engine(), TEST_OWNER)
    parsed = parse(f"times.{format}", temporal_file(format))
    dataset = repository.create(f"Temporal {uuid4()}", parsed)
    table = dataset.table.physical_table_name
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SHOW TimeZone")) == writer_timezone
            types = dict(
                connection.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema='uploaded_data' AND table_name=:table"
                    ),
                    {"table": table},
                ).all()
            )
            assert types["ngay"] == "date"
            assert types["local"] == "timestamp without time zone"
            assert types["instant"] == "timestamp with time zone"
            rows = (
                connection.execute(text(f'SELECT * FROM uploaded_data."{table}" ORDER BY ma'))
                .mappings()
                .all()
            )
            for actual, expected in zip(rows, TEMPORAL_ROWS, strict=True):
                assert type(actual["ngay"]) is date
                assert actual["ngay"] == date.fromisoformat(expected[1])
                assert actual["local"] == datetime.fromisoformat(expected[2])
                assert actual["local"].tzinfo is None
                expected_instant = datetime.fromisoformat(expected[3].replace("Z", "+00:00"))
                assert actual["instant"] == expected_instant
        context = build_dataset_sql_context(dataset)
        assert "instant TIMESTAMPTZ" in context.schema_context
        validator = SqlValidator(context.table_columns, context.allowed_schemas, max_tables=1)
        executor = SqlExecutor(get_readonly_engine(), 5000, 100)
        for start, end, total in [
            ("2026-10-01", "2026-11-01", 50),
            ("2027-01-01", "2027-02-01", 100),
        ]:
            for column, literal, suffix in [
                ("instant", "TIMESTAMPTZ", "+07:00"),
                ("local", "TIMESTAMP", ""),
                ("ngay", "DATE", ""),
            ]:
                statement = validator.validate(
                    f"SELECT COUNT(*) AS n FROM uploaded_data.{table} "
                    f"WHERE {column} >= {literal} '{start}{suffix}' "
                    f"AND {column} < {literal} '{end}{suffix}'"
                )
                assert executor.execute(statement) == [{"n": 2}]
            with engine.connect() as connection:
                assert (
                    connection.scalar(
                        text(
                            f"SELECT SUM(amount) FROM uploaded_data.{table} "
                            "WHERE instant >= CAST(:start AS TIMESTAMPTZ) "
                            "AND instant < CAST(:end AS TIMESTAMPTZ)"
                        ),
                        {"start": f"{start}+07:00", "end": f"{end}+07:00"},
                    )
                    == total
                )
    finally:
        repository.delete(dataset.dataset_id)
        engine.dispose()


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_guest_temp_import_uses_same_temporal_mapping(format: str) -> None:
    settings = get_settings()
    require_test_database(settings.database_setup_url)
    configure_guest_access(get_setup_engine())
    file = parse_guest_file(f"times.{format}", temporal_file(format), None, settings)
    database = GuestSqlDatabase(settings, [file])
    try:
        with database.engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT pg_typeof(instant)::text FROM pg_temp.table_1 LIMIT 1")
                )
                == "timestamp with time zone"
            )
            assert connection.scalar(
                text("SELECT instant FROM pg_temp.table_1 WHERE ma='B'")
            ) == datetime.fromisoformat("2026-10-01T00:00:00+07:00")
        validator = SqlValidator(
            {"table_1": {c.name for c in file.table.columns}},
            {"table_1": "pg_temp"},
            max_tables=1,
        )
        query = validator.validate(
            "SELECT COUNT(*) AS n FROM pg_temp.table_1 "
            "WHERE instant >= TIMESTAMPTZ '2027-01-01 00:00:00+07:00' "
            "AND instant < TIMESTAMPTZ '2027-02-01 00:00:00+07:00'"
        )
        assert SqlExecutor(database.engine, 3000, 100).execute(query) == [{"n": 2}]
    finally:
        database.close()


@pytest.mark.usefixtures("contract_session")
def test_numeric_db_api_preview_and_history_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = get_setup_engine()
    require_test_database(get_settings().database_setup_url)
    repository = DatasetRepository(engine, get_readonly_engine(), TEST_OWNER)
    parsed = parse(
        "numeric.csv",
        (
            "Mã,Amount\nA,12345678901234567890.12\nB,0.000000000000000000000002\nC,0.00\nD,\n"
        ).encode(),
    )
    dataset = repository.create(f"Numeric {uuid4()}", parsed)
    conversations = ConversationRepository(engine, TEST_OWNER)
    conversation = conversations.create(dataset.dataset_id)
    try:
        context = build_dataset_sql_context(dataset)
        validator = SqlValidator(context.table_columns, context.allowed_schemas, max_tables=1)
        sql = validator.validate(
            f"SELECT SUM(amount) AS total, AVG(amount) AS average, COUNT(*) AS n, "
            f"COUNT(amount) AS present FROM uploaded_data.{dataset.table.physical_table_name}"
        )
        rows = SqlExecutor(get_readonly_engine(), 5000, 100).execute(sql)
        with engine.connect() as connection:
            raw = connection.execute(text(sql.statement)).mappings().one()
        assert raw["total"] == Decimal("12345678901234567890.120000000000000000000002")
        assert rows == [
            {
                "total": format(raw["total"], "f"),
                "average": format(raw["average"], "f"),
                "n": 4,
                "present": 3,
            }
        ]
        assert repository.preview_rows(dataset.dataset_id) == [
            {"Mã": "A", "Amount": "12345678901234567890.12"},
            {"Mã": "B", "Amount": "0.000000000000000000000002"},
            {"Mã": "C", "Amount": "0.00"},
            {"Mã": "D", "Amount": None},
        ]

        class Service:
            def chat(self, question: str) -> ChatResult:
                return ChatResult("Synthetic numeric result", RouteLabel.SQL, sql.statement, rows)

        monkeypatch.setattr("app.api.routes.build_chat_service", lambda settings: Service())
        response = TestClient(app).post("/api/chat", json={"message": "Numeric fixture"})
        assert response.status_code == 200
        assert response.json()["rows"] == rows
        conversations.add_response_message(
            conversation.conversation_id,
            content=response.json()["answer"],
            response_metadata=response.json(),
            is_error=False,
        )
        restored = conversations.get(conversation.conversation_id)
        assert restored.messages[0].response_metadata["rows"] == rows
    finally:
        conversations.delete(conversation.conversation_id)
        repository.delete(dataset.dataset_id)


def test_valid_alias_queries_match_postgres_name_precedence() -> None:
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    require_test_database(get_settings().database_setup_url)
    parsed = parse("aliases.csv", b"Amount,Label\n2,b\n1,a\n2,b\n")
    dataset = repository.create(f"Aliases {uuid4()}", parsed)
    try:
        context = build_dataset_sql_context(dataset)
        validator = SqlValidator(context.table_columns, context.allowed_schemas, max_tables=1)
        executor = SqlExecutor(get_readonly_engine(), 5000, 100)
        cases = [
            (
                "SELECT amount AS salary FROM {table} ORDER BY salary",
                [{"salary": 1}, {"salary": 2}, {"salary": 2}],
            ),
            (
                "SELECT label AS g, SUM(amount) AS total FROM {table} GROUP BY g ORDER BY total",
                [{"g": "a", "total": "1"}, {"g": "b", "total": "4"}],
            ),
            (
                "SELECT MIN(amount) AS label, COUNT(*) AS n FROM {table} "
                "GROUP BY label ORDER BY label",
                [{"label": 1, "n": 1}, {"label": 2, "n": 2}],
            ),
            (
                "SELECT -amount AS amount FROM {table} ORDER BY amount",
                [{"amount": -2}, {"amount": -2}, {"amount": -1}],
            ),
            (
                "SELECT amount AS x, amount AS x FROM {table} GROUP BY x ORDER BY x",
                [{"x": 1}, {"x": 2}],
            ),
            (
                "SELECT t.amount FROM {table} t ORDER BY t.amount",
                [{"amount": 1}, {"amount": 2}, {"amount": 2}],
            ),
        ]
        for sql, expected in cases:
            validated = validator.validate(
                sql.format(table=f"uploaded_data.{dataset.table.physical_table_name}")
            )
            assert executor.execute(validated) == expected
    finally:
        repository.delete(dataset.dataset_id)
