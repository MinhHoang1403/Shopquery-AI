"""Anonymous capability, quotas and RAM lifecycle without live providers or a database."""

import asyncio
import os
import time
from contextlib import nullcontext
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.guest.pipeline import GeneralChat, GeneralDraft, MemoryChunks
from app.guest.store import GuestFile, GuestStore
from app.guest.worker import parse_guest_file, run_isolated
from app.main import app
from app.routing.service import ChatResult
from tests.test_dataset_parser import xlsx_bytes
from tests.test_document_upload_parser import _docx_bytes, _pdf_bytes


@pytest.fixture
def guest_api(monkeypatch):
    settings = Settings(
        _env_file=None,
        beta_provider_data_enabled=True,
        guest_ai_enabled=True,
        inetcloud_base_url="https://example.invalid",
        guest_chat_per_ip_hour=6,
    )
    store = GuestStore(settings)
    rates = {}

    def rate(ip, action, limit):
        key = (ip, action)
        rates[key] = rates.get(key, 0) + 1
        if rates[key] > limit:
            raise HTTPException(429, "Guest IP budget exceeded")

    control = SimpleNamespace(ip_rate=rate, lease=lambda *args: nullcontext())
    monkeypatch.setattr("app.guest.routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.guest.routes.guest_store", lambda: store)
    monkeypatch.setattr("app.guest.routes.guest_control", lambda: control)
    worker = Mock(
        side_effect=lambda action, payload, config, cancel: (
            parse_guest_file(*payload, config)
            if action == "parse"
            else []
            if action == "detect_relationships"
            else ChatResult("Explanation", None)
        )
    )
    monkeypatch.setattr("app.guest.routes.run_isolated", worker)
    client = TestClient(app, headers={"Origin": settings.app_origin})
    yield SimpleNamespace(client=client, store=store, settings=settings, worker=worker)
    client.close()
    store.close()


def new_guest(api):
    response = api.client.post("/api/guest/session", json={})
    assert response.status_code == 200
    body = response.json()
    return {"X-Guest-Token": body["token"], "X-Guest-CSRF": body["csrf_token"]}


def test_guest_needs_origin_capability_and_csrf_not_a_google_cookie(guest_api):
    api = guest_api
    assert (
        api.client.post(
            "/api/guest/session", json={}, headers={"Origin": "https://other.invalid"}
        ).status_code
        == 403
    )
    headers = new_guest(api)
    assert api.client.get("/api/guest/limits", headers=headers).status_code == 200
    assert api.client.get("/api/guest/limits").status_code == 401
    assert (
        api.client.get(
            "/api/guest/limits", headers={"X-Guest-Token": headers["X-Guest-Token"]}
        ).status_code
        == 403
    )
    assert api.client.get("/api/datasets", headers=headers).status_code == 401
    assert api.client.get("/api/conversations", headers=headers).status_code == 401
    assert (
        api.client.post("/api/chat", headers=headers, json={"message": "Question"}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "extra", [{"dataset_id": 1}, {"owner_user_id": "A"}, {"conversation_id": "B"}]
)
def test_guest_cannot_supply_private_resource_identifiers(guest_api, extra):
    api = guest_api
    headers = new_guest(api)
    assert (
        api.client.post(
            "/api/guest/chat", headers=headers, json={"message": "Question", **extra}
        ).status_code
        == 422
    )
    api.worker.assert_not_called()


def test_quota_is_enforced_before_worker_and_refresh_still_has_ip_budget(guest_api):
    api = guest_api
    first = new_guest(api)
    for _ in range(5):
        assert (
            api.client.post(
                "/api/guest/chat", headers=first, json={"message": "Explain SQL"}
            ).status_code
            == 200
        )
    assert (
        api.client.post("/api/guest/chat", headers=first, json={"message": "One more"}).status_code
        == 429
    )
    second = new_guest(api)
    assert (
        api.client.post("/api/guest/chat", headers=second, json={"message": "New page"}).status_code
        == 200
    )
    assert (
        api.client.post(
            "/api/guest/chat", headers=second, json={"message": "Refresh bypass"}
        ).status_code
        == 429
    )
    assert api.worker.call_count == 6


@pytest.mark.parametrize("flag", ["beta_provider_data_enabled", "guest_ai_enabled"])
def test_provider_gates_precede_worker_and_question_consumption(guest_api, flag):
    api = guest_api
    setattr(api.settings, flag, False)
    headers = new_guest(api)
    assert (
        api.client.post(
            "/api/guest/chat", headers=headers, json={"message": "Explain SQL"}
        ).status_code
        == 403
    )
    assert api.client.get("/api/guest/limits", headers=headers).json()["remaining"] == 5
    api.worker.assert_not_called()


def test_uploads_are_ram_scoped_and_reset_or_new_page_cannot_restore_them(guest_api):
    api = guest_api
    a, b = new_guest(api), new_guest(api)
    response = api.client.post(
        "/api/guest/files?filename=fees.csv", headers=a, content=b"Name,Fee\nA,100\nB,200\n"
    )
    assert response.status_code == 200
    assert response.json()["preview"]["row_count"] == 2
    assert api.client.get("/api/guest/limits", headers=b).json()["files"] == []
    fresh = new_guest(api)
    assert api.client.get("/api/guest/limits", headers=fresh).json()["files"] == []
    assert api.client.post("/api/guest/reset", headers=a, json={}).status_code == 204
    assert api.client.get("/api/guest/limits", headers=a).status_code == 410
    assert api.client.get("/api/guest/limits", headers=b).status_code == 200


def test_previews_do_not_spend_the_commit_budget(guest_api):
    api = guest_api
    api.settings.guest_uploads_per_ip_hour = 1
    headers = new_guest(api)
    for _ in range(3):
        response = api.client.post(
            "/api/guest/files/preview?filename=fees.csv",
            headers=headers,
            content=b"Name,Fee\nA,100\n",
        )
        assert response.status_code == 200
    response = api.client.post(
        "/api/guest/files?filename=fees.csv", headers=headers, content=b"Name,Fee\nA,100\n"
    )
    assert response.status_code == 200
    assert len(response.json()["status"]["files"]) == 1
    assert (
        api.client.post(
            "/api/guest/files?filename=next.csv", headers=headers, content=b"Name,Fee\nB,200\n"
        ).status_code
        == 429
    )


def test_guest_parse_budget_is_session_scoped_and_bounds_invalid_attempts(guest_api):
    api = guest_api
    api.settings.guest_previews_per_session = 2
    first, second = new_guest(api), new_guest(api)
    parse = api.worker.side_effect
    api.worker.side_effect = HTTPException(422, "Unsupported file")
    for _ in range(2):
        assert (
            api.client.post(
                "/api/guest/files/preview?filename=bad.exe", headers=first, content=b"bad"
            ).status_code
            == 422
        )
    blocked = api.client.post(
        "/api/guest/files/preview?filename=x.csv", headers=first, content=b"A\n1\n"
    )
    assert blocked.status_code == 429
    assert blocked.headers["X-Guest-Limit"] == "preview"
    assert api.client.get("/api/guest/limits", headers=first).json()["remaining"] == 5
    api.worker.side_effect = parse
    assert (
        api.client.post(
            "/api/guest/files?filename=x.csv", headers=second, content=b"A\n1\n"
        ).status_code
        == 200
    )


def test_file_and_json_caps_fail_before_processing(guest_api):
    api = guest_api
    headers = new_guest(api)
    assert (
        api.client.post(
            "/api/guest/files?filename=x.csv&dataset_id=1", headers=headers, content=b"A\n1\n"
        ).status_code
        == 422
    )
    assert (
        api.client.post(
            "/api/guest/files?filename=x.csv",
            headers=headers,
            content=b"x" * (api.settings.guest_max_file_bytes + 1),
        ).status_code
        == 413
    )
    assert (
        api.client.post(
            "/api/guest/chat", headers=headers, json={"message": "x" * 9000}
        ).status_code
        == 413
    )
    api.worker.assert_not_called()


def test_expiration_cleanup_cancels_work_reclaims_files_and_has_no_recovery():
    now = [0.0]
    settings = Settings(_env_file=None, guest_max_sessions=1, guest_max_total_bytes=1024)
    store = GuestStore(settings, lambda: now[0])
    raw, context = store.create()
    store.add_file(context, GuestFile("1", "policy.md", 10, 600))
    with pytest.raises(HTTPException):
        store.add_file(context, GuestFile("2", "large.md", 10, 600))
    with store.operation(context), pytest.raises(HTTPException), store.operation(context):
        pytest.fail("Concurrent guest operation admitted")
    now[0] = 601
    store.cleanup()
    assert context.cancelled.is_set() and context.files == []
    with pytest.raises(HTTPException):
        store.get(raw)
    store.create()
    with pytest.raises(HTTPException):
        GuestStore(settings).get(raw)


def test_general_chat_requires_data_instead_of_echoing_invented_numbers():
    gateway = SimpleNamespace(
        generate_structured=lambda *args: GeneralDraft(
            requires_data=True,
            in_scope=True,
            answer="Invented revenue 12345",
        )
    )
    result = GeneralChat(gateway).chat("My revenue?")
    assert "12345" not in result.answer
    assert result.route is None and not result.rows and not result.sources and result.sql is None


def sleeping_worker(connection, action, payload, settings):
    time.sleep(20)


def crashed_worker(connection, action, payload, settings):
    os._exit(7)


def test_disposable_parser_success_timeout_and_crash_cleanup():
    settings = Settings(_env_file=None, guest_parse_timeout_seconds=1)
    with pytest.raises(HTTPException) as timeout:
        run_isolated("parse", (), settings, Event(), target=sleeping_worker)
    assert timeout.value.status_code == 504
    with pytest.raises(HTTPException) as crash:
        run_isolated(
            "parse",
            (),
            settings.model_copy(update={"guest_parse_timeout_seconds": 10}),
            Event(),
            target=crashed_worker,
        )
    assert crash.value.status_code == 502
    parsed = run_isolated(
        "parse",
        ("fees.csv", b"Fee\n100\n200\n", None),
        settings.model_copy(update={"guest_parse_timeout_seconds": 10}),
        Event(),
    )
    assert parsed.table.row_count == 2


def test_memory_retrieval_does_not_accept_any_persistent_dataset_id():
    with pytest.raises(Exception, match="persistent dataset"):
        MemoryChunks([], None).retrieve([1.0] * 768, dataset_id=1)


def test_failed_generation_returns_no_fabricated_result_and_reports_consumed_quota(guest_api):
    api = guest_api
    headers = new_guest(api)
    api.worker.side_effect = HTTPException(502, "Provider unavailable; no result")
    response = api.client.post("/api/guest/chat", headers=headers, json={"message": "Explain SQL"})
    assert response.status_code == 502
    assert response.headers["X-Guest-Remaining"] == "4"
    assert "response" not in response.json() and "answer" not in response.json()
    assert api.client.get("/api/guest/limits", headers=headers).json()["remaining"] == 4


@pytest.mark.parametrize("extension", ["csv", "xlsx", "pdf", "docx", "txt", "md"])
def test_all_guest_file_types_parse_without_provider_calls(extension):
    settings = Settings(_env_file=None, beta_provider_data_enabled=False, guest_ai_enabled=False)
    content = {
        "csv": b"Fee\n100\n200\n",
        "xlsx": xlsx_bytes([["Fee"], [100], [200]]),
        "pdf": _pdf_bytes("Temporary rules: fee threshold is 250."),
        "docx": _docx_bytes("Ngưỡng học phí 250."),
        "txt": b"Temporary rules: fee threshold is 250.",
        "md": b"# Rules\n\nFee threshold is 250.",
    }[extension]
    parsed = parse_guest_file(f"test.{extension}", content, None, settings)
    assert parsed.table.row_count == 2 if extension in {"csv", "xlsx"} else bool(parsed.chunks)


def test_background_ttl_cleanup_and_shutdown_release_guest_data(monkeypatch):
    from app.main import lifespan

    now = [0.0]
    settings = Settings(_env_file=None, guest_cleanup_seconds=1)
    store = GuestStore(settings, lambda: now[0])
    _, context = store.create()
    store.add_file(context, GuestFile("1", "temporary.md", 10, 100))
    monkeypatch.setattr("app.main.guest_store", lambda: store)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    async def check():
        async with lifespan(app):
            now[0] = 601
            await asyncio.sleep(1.1)
            assert context.cancelled.is_set() and not context.files
            _, live = store.create()
        assert live.cancelled.is_set()

    asyncio.run(check())
