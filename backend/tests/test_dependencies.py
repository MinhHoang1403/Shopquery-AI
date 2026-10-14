"""Tests for application dependency construction."""

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

from app.dependencies import ensure_application_schema


def test_schema_initialization_is_serialized(monkeypatch) -> None:
    ensure_application_schema.cache_clear()
    counter_lock = Lock()
    active_calls = 0
    highest_concurrency = 0

    def create_schema(_engine: object) -> None:
        nonlocal active_calls, highest_concurrency
        with counter_lock:
            active_calls += 1
            highest_concurrency = max(highest_concurrency, active_calls)
        sleep(0.05)
        with counter_lock:
            active_calls -= 1

    monkeypatch.setattr("app.dependencies.get_setup_engine", lambda: object())
    monkeypatch.setattr("app.dependencies.create_schema", create_schema)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(ensure_application_schema, "postgresql://test")
            for _ in range(2)
        ]
        for future in futures:
            future.result()

    ensure_application_schema.cache_clear()
    assert highest_concurrency == 1
