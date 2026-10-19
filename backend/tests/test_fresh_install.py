"""Fresh schema and ownership constraints on a disposable database, never main."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.auth.repository import AuthRepository
from app.database.fresh import FRESH_VERSION, initialize_fresh_database
from app.database.models import Base
from app.database.session import get_setup_engine
from app.database.test_safety import require_test_database
from app.datasets.repository import DatasetRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def fresh_engine():
    parent = get_setup_engine()
    require_test_database(parent.url.render_as_string(hide_password=False))
    name = "shopquery_test_fresh_" + uuid4().hex
    with parent.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(parent.url.set(database=name))
    try:
        yield engine
    finally:
        engine.dispose()
        assert name.startswith("shopquery_test_fresh_") and len(name) == 53
        with parent.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE "{name}"'))


def test_fresh_install_is_empty_and_enforces_owner_scoping(fresh_engine):
    engine = fresh_engine
    initialize_fresh_database(engine)
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            assert connection.scalar(text(f'SELECT count(*) FROM "{table.name}"')) == 0
        assert connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        assert connection.scalar(text("SELECT version FROM schema_migrations")) == FRESH_VERSION
        for table in ("users", "user_sessions", "oidc_flows", "chat_messages", "schema_migrations"):
            assert not connection.scalar(
                text("SELECT has_table_privilege('shopquery_reader', :table, 'SELECT')"),
                {"table": table},
            )
    auth = AuthRepository(engine)
    a = auth.identity(uuid4().hex, "a@example.invalid", "A")
    b = auth.identity(uuid4().hex, "b@example.invalid", "B")
    repo = DatasetRepository(engine, engine, a)
    assert not repo.has_demo_data()
    workspace = repo.create_workspace("My data")
    assert DatasetRepository(engine, engine, b).list() == []
    assert all(
        not col["nullable"]
        for col in inspect(engine).get_columns("datasets")
        if col["name"] == "owner_user_id"
    )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO chat_conversations "
                "(conversation_id, owner_user_id, dataset_id, title, title_customized) "
                "VALUES (:id, :owner, :dataset, 'Wrong owner', false)"
            ),
            {"id": uuid4(), "owner": b, "dataset": workspace.dataset_id},
        )
    initialize_fresh_database(engine)
    assert repo.get(workspace.dataset_id).name == "My data"


def test_fresh_install_refuses_an_existing_unmarked_database(fresh_engine):
    with fresh_engine.begin() as connection:
        connection.execute(text("CREATE TABLE existing_data(value INTEGER)"))
        connection.execute(text("INSERT INTO existing_data VALUES (42)"))
    with pytest.raises(ValueError, match="without application tables"):
        initialize_fresh_database(fresh_engine)
    with fresh_engine.connect() as connection:
        assert connection.scalar(text("SELECT value FROM existing_data")) == 42
        assert connection.scalar(text("SELECT to_regclass('public.users')")) is None
