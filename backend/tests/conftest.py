"""Shared test fixtures."""

import os

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.getenv("RUN_DATABASE_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_DATABASE_TESTS=1 with PostgreSQL running")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
