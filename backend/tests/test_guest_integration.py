"""Real isolated PostgreSQL TEMP/read-only execution, no Google or AI calls."""

import os
import time
from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.errors import SqlValidationError
from app.database.guest_access import configure_guest_access
from app.database.integrity import legacy_fingerprints
from app.database.models import ResourceLimit
from app.database.session import get_setup_engine
from app.guest.limits import GuestControl
from app.guest.pipeline import GuestSqlDatabase, run_guest_chat
from app.guest.worker import parse_guest_file, run_isolated
from app.rag.pipeline import RagAnswerDraft
from app.routing.hybrid import HybridAnswerDraft
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.generator import SqlDraft

pytestmark = pytest.mark.integration


@pytest.fixture
def guest_settings():
    engine = get_setup_engine()
    configure_guest_access(engine)
    configure_guest_access(engine)
    return get_settings()


class GuestGateway:
    def __init__(self, route, unsafe=False):
        self.route, self.unsafe = route, unsafe

    def generate_structured(self, prompt, schema):
        if schema is RouteDecision:
            return RouteDecision(route=self.route, reason="Fake gateway, real isolated sources")
        if schema is SqlDraft:
            return SqlDraft(
                sql="SELECT count(*) FROM public.users"
                if self.unsafe
                else "SELECT SUM(fee) AS total FROM pg_temp.table_1"
            )
        if schema is RagAnswerDraft:
            return RagAnswerDraft(answer="Ngưỡng là 250.", used_chunk_ids=[1])
        if schema is HybridAnswerDraft:
            return HybridAnswerDraft(answer="Tổng 300 vượt ngưỡng 250.", used_chunk_ids=[1])
        raise AssertionError("Unexpected generation schema")

    def generate_text(self, prompt):
        return "Tổng học phí là 300."


class OfflineEmbedder:
    def embed_query(self, question):
        return [1.0] + [0.0] * 767

    def embed_document(self, title, content):
        return self.embed_query(content)


@pytest.mark.parametrize("route", [RouteLabel.SQL, RouteLabel.RAG, RouteLabel.HYBRID])
def test_guest_pipelines_use_real_temp_rows_and_ram_citations_without_persistence(
    guest_settings, route
):
    settings = guest_settings
    engine = get_setup_engine()
    before = legacy_fingerprints(engine)
    files = [
        parse_guest_file("fees.csv", b"Fee\n100\n200\n", None, settings),
        parse_guest_file(
            "rules.md", "# Quy định\n\nNgưỡng nhắc phí là 250.".encode(), None, settings
        ),
    ]
    result = run_guest_chat(
        files, "Kiểm tra", settings, gateway=GuestGateway(route), embedder=OfflineEmbedder()
    )
    assert result.route == route
    if route in {RouteLabel.SQL, RouteLabel.HYBRID}:
        assert result.rows == [{"total": "300"}]
        assert "pg_temp.table_1" in result.sql
    if route in {RouteLabel.RAG, RouteLabel.HYBRID}:
        assert result.sources[0].source_file == "rules.md"
        assert "250" in result.sources[0].content
    assert legacy_fingerprints(engine) == before
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid "
                    "WHERE n.nspname LIKE 'pg_temp_%' AND c.relname='table_1'"
                )
            )
            == 0
        )


def test_guest_role_and_validator_cannot_read_personal_data_or_other_guest_tables(guest_settings):
    s = guest_settings
    a = GuestSqlDatabase(s, [parse_guest_file("a.csv", b"Fee\n100\n", None, s)])
    b = GuestSqlDatabase(s, [parse_guest_file("b.csv", b"Fee\n900\n", None, s)])
    try:
        with a.engine.connect() as connection:
            assert connection.scalar(text("SELECT SUM(fee) FROM pg_temp.table_1")) == 100
            own_schema = connection.scalar(
                text("SELECT nspname FROM pg_namespace WHERE oid=pg_my_temp_schema()")
            )
        with b.engine.connect() as connection:
            assert connection.scalar(text("SELECT SUM(fee) FROM pg_temp.table_1")) == 900
        with pytest.raises(DBAPIError), b.engine.connect() as connection:
            connection.execute(text("SELECT * FROM public.users"))
        with pytest.raises(DBAPIError), b.engine.connect() as connection:
            connection.execute(text(f'SELECT * FROM "{own_schema}".table_1'))
        with pytest.raises(DBAPIError), b.engine.connect() as connection:
            connection.execute(text("CREATE TABLE public.guest_not_allowed(value integer)"))
    finally:
        a.close()
        b.close()
    with pytest.raises(SqlValidationError):
        run_guest_chat(
            [parse_guest_file("a.csv", b"Fee\n100\n", None, s)],
            "Unsafe",
            s,
            gateway=GuestGateway(RouteLabel.SQL, unsafe=True),
        )


def test_guest_limits_are_ip_persistent_and_concurrency_is_global_without_fake_users(
    guest_settings,
):
    engine = get_setup_engine()
    settings = guest_settings.model_copy(update={"guest_system_concurrency": 1})
    control = GuestControl(engine, settings)
    key = uuid4().hex
    control.ip_rate(key, "chat", 1)
    with pytest.raises(HTTPException):
        GuestControl(engine, settings).ip_rate(key, "chat", 1)
    with control.lease(key, settings), pytest.raises(HTTPException):
        GuestControl(engine, settings).lease(uuid4().hex, settings).__enter__()
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(ResourceLimit)
                .where(ResourceLimit.key.startswith("guest:lease:"))
            )
            == 0
        )


def crash_with_temp_table(connection, action, payload, settings):
    database = GuestSqlDatabase(
        settings, [parse_guest_file("crash.csv", b"Fee\n100\n", None, settings)]
    )
    with database.engine.connect() as sql:
        connection.send((True, sql.scalar(text("SELECT pg_backend_pid()"))))
    os._exit(9)


def test_guest_process_exit_closes_its_real_temp_connection(guest_settings):
    pid = run_isolated("chat", (), guest_settings, Event(), target=crash_with_temp_table)
    deadline = time.monotonic() + 3
    with get_setup_engine().connect() as connection:
        while connection.scalar(
            text("SELECT count(*) FROM pg_stat_activity WHERE pid=:pid"), {"pid": pid}
        ):
            assert time.monotonic() < deadline, "Guest SQL connection survived worker exit"
            connection.rollback()
            time.sleep(0.05)
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname LIKE 'pg_temp_%' AND c.relname='table_1'"
                )
            )
            == 0
        )
