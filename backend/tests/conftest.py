"""Shared test fixtures."""

import os

import pytest

from app.core.config import get_settings
from app.database.test_safety import require_test_database
from tests.auth_helpers import contract_session  # noqa: F401


@pytest.fixture(autouse=True)
def integration_owner(request):
    if "integration" not in request.node.keywords or os.getenv("RUN_DATABASE_TESTS") != "1":
        return
    from sqlalchemy.dialects.postgresql import insert

    from app.database.models import User
    from app.database.session import get_setup_engine
    from app.database.setup import create_schema
    from tests.auth_helpers import TEST_OWNER

    engine = get_setup_engine()
    require_test_database(engine.url.render_as_string(hide_password=False))
    create_schema(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(User)
            .values(
                user_id=TEST_OWNER,
                issuer="https://accounts.google.com",
                subject="contract-owner",
                email="contract@example.invalid",
                display_name="Contract owner",
                active=True,
            )
            .on_conflict_do_nothing()
        )


def pytest_runtest_setup(item: pytest.Item) -> None:
    if "integration" in item.keywords and os.getenv("RUN_DATABASE_TESTS") == "1":
        require_test_database(get_settings().database_setup_url)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.getenv("RUN_DATABASE_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_DATABASE_TESTS=1 with PostgreSQL running")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
