"""Shared test fixtures."""

import os

import httpx
import pytest

from app.core.config import get_settings
from app.database.test_safety import require_test_database
from tests.auth_helpers import contract_session  # noqa: F401


@pytest.fixture(autouse=True)
def offline_http_boundary(request, monkeypatch):
    if "live" in request.node.keywords:
        return

    def blocked(*args, **kwargs):
        raise AssertionError("Offline tests cannot use a real HTTP transport")

    async def async_blocked(*args, **kwargs):
        raise AssertionError("Offline tests cannot use a real HTTP transport")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)


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
    golden_files = {
        "test_providers.py",
        "test_error_contract.py",
        "test_generation_contract.py",
        "test_contract_conversion.py",
        "test_plan_binding.py",
        "test_compiler_diagnostics.py",
        "test_category_grouping.py",
        "test_category_results_integration.py",
        "test_count_conformance.py",
        "test_evidence_coverage.py",
        "test_verified_conversation_contract.py",
        "test_conversation_context.py",
        "test_document_upload_integration.py",
        "test_hybrid_evidence_integration.py",
        "test_decimal_contract.py",
        "test_result_presentation.py",
        "test_reliability_properties.py",
        "test_reliability_properties_integration.py",
        "test_plan_security.py",
        "test_provider_usage.py",
    }
    for item in items:
        if item.path.name in golden_files:
            item.add_marker(pytest.mark.reliability_golden)
    if os.getenv("RUN_DATABASE_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_DATABASE_TESTS=1 with PostgreSQL running")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
