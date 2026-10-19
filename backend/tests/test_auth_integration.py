"""Real PostgreSQL sessions and A/B resource isolation without any live provider."""

import re
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select, text, update

from app.auth.limits import ResourceControl
from app.auth.repository import AuthRepository, csrf_token, token_hash
from app.conversations.repository import ConversationRepository
from app.core.config import get_settings
from app.core.errors import ResourceConflictError, ResourceNotFoundError, SqlValidationError
from app.database.models import DocumentChunk, OidcFlow, User, UserSession
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.context import build_dataset_sql_context
from app.datasets.parser import parse_tabular_file
from app.datasets.repository import DatasetRepository
from app.main import app
from app.rag.repository import DocumentRepository
from app.rag.upload_parser import parse_document_file
from app.text_to_sql.validator import SqlValidator

pytestmark = pytest.mark.integration


class OfflineEmbedder:
    def embed_document(self, title, content):
        return [1.0, *([0.0] * 767)]


@pytest.fixture
def accounts(monkeypatch):
    engine, reader = get_setup_engine(), get_readonly_engine()
    auth = AuthRepository(engine)
    emails = [f"{uuid4().hex}@example.invalid" for _ in range(2)]
    settings = get_settings().model_copy(
        update={
            "auth_invited_emails": emails,
            "beta_provider_data_enabled": True,
            "beta_max_datasets": 20,
            "beta_chat_per_user_hour": 1000,
            "beta_upload_per_user_hour": 1000,
        }
    )
    for module in ("app.auth.dependencies", "app.auth.routes", "app.auth.limits", "app.api.routes"):
        monkeypatch.setattr(f"{module}.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth.dependencies.auth_repository", lambda: auth)
    monkeypatch.setattr("app.auth.routes.auth_repository", lambda: auth)
    monkeypatch.setattr(
        "app.api.routes.resource_control", lambda: ResourceControl(engine, settings)
    )
    monkeypatch.setattr(
        "app.auth.routes.resource_control", lambda: ResourceControl(engine, settings)
    )
    result = []
    for index, email in enumerate(emails):
        user_id = auth.identity(uuid4().hex, email, f"Account {index}")
        raw = auth.create_session(user_id, 1)
        datasets = DatasetRepository(engine, reader, user_id)
        dataset = datasets.create(
            "Sales",
            parse_tabular_file(
                "sales.csv",
                f"Value\n{(index + 1) * 100}\n".encode(),
                max_bytes=1000,
                max_rows=10,
                max_columns=10,
            ),
        )
        documents = DocumentRepository(engine, reader, user_id)
        document = documents.add_document(
            dataset.dataset_id,
            parse_document_file(
                "policy.md",
                f"# Policy\n\nPrivate account {index}.".encode(),
                max_bytes=1000,
            ),
            OfflineEmbedder(),
        )
        chats = ConversationRepository(engine, user_id)
        conversation = chats.create(dataset.dataset_id)
        client = TestClient(
            app,
            cookies={settings.session_cookie_name: raw},
            headers={
                "Origin": settings.app_origin,
                "X-CSRF-Token": csrf_token(raw),
            },
        )
        result.append(
            SimpleNamespace(
                user_id=user_id,
                raw=raw,
                datasets=datasets,
                dataset=dataset,
                documents=documents,
                document=document,
                chats=chats,
                conversation=conversation,
                client=client,
            )
        )
    yield SimpleNamespace(a=result[0], b=result[1], auth=auth, engine=engine, settings=settings)
    for account in result:
        account.client.close()
        for conversation in account.chats.list(100, 0):
            account.chats.delete(conversation.conversation_id)
        for dataset in account.datasets.list():
            with suppress(ResourceNotFoundError):
                account.datasets.delete(dataset.dataset_id, delete_conversations=True)


@pytest.mark.parametrize(
    "operation",
    [
        "dataset",
        "preview",
        "tables",
        "table_preview",
        "table_import",
        "document_upload",
        "documents",
        "document",
        "document_delete",
        "table_delete",
        "dataset_delete",
        "conversation",
        "conversation_patch",
        "conversation_delete",
        "conversation_message",
        "conversation_create",
        "SQL",
        "RAG",
        "HYBRID",
    ],
)
def test_account_cannot_access_other_resources_or_start_work(accounts, monkeypatch, operation):
    a, b = accounts.a, accounts.b

    def forbidden(*args, **kwargs):
        pytest.fail("Unauthorized request reached schema/parser/provider/embedding/SQL work")

    for name in (
        "build_chat_service",
        "build_dataset_chat_service",
        "build_dataset_sql_context",
        "GeminiGateway",
        "parse_document_file",
        "parse_tabular_file",
    ):
        monkeypatch.setattr(f"app.api.routes.{name}", forbidden)
    dataset_path = f"/api/datasets/{b.dataset.dataset_id}"
    document_path = f"{dataset_path}/documents/{b.document.document_id}"
    chat_path = f"/api/conversations/{b.conversation.conversation_id}"
    operations = {
        "dataset": ("GET", dataset_path, {}),
        "preview": ("GET", dataset_path + "/preview", {}),
        "tables": ("GET", dataset_path + "/tables", {}),
        "table_preview": (
            "POST",
            dataset_path + "/tables/preview",
            {"files": {"file": ("sales.csv", b"Value\n1\n")}},
        ),
        "table_import": (
            "POST",
            dataset_path + "/tables/import",
            {"files": {"file": ("sales.csv", b"Value\n1\n")}},
        ),
        "document_upload": (
            "POST",
            dataset_path + "/documents",
            {"files": {"file": ("policy.md", b"# Policy\n\nText")}},
        ),
        "documents": ("GET", dataset_path + "/documents", {}),
        "document": ("GET", document_path, {}),
        "document_delete": ("DELETE", document_path, {}),
        "table_delete": (
            "DELETE",
            dataset_path + f"/tables/{b.dataset.table.dataset_table_id}",
            {},
        ),
        "dataset_delete": ("DELETE", dataset_path + "?delete_conversations=true", {}),
        "conversation": ("GET", chat_path, {}),
        "conversation_patch": ("PATCH", chat_path, {"json": {"title": "stolen"}}),
        "conversation_delete": ("DELETE", chat_path, {}),
        "conversation_message": ("POST", chat_path + "/messages", {"json": {"message": "Q"}}),
        "conversation_create": (
            "POST",
            "/api/conversations",
            {"json": {"dataset_id": b.dataset.dataset_id}},
        ),
    }
    if operation in {"SQL", "RAG", "HYBRID"}:
        response = a.client.post(
            "/api/chat", json={"message": operation, "dataset_id": b.dataset.dataset_id}
        )
    else:
        method, path, kwargs = operations[operation]
        response = a.client.request(method, path, **kwargs)
    assert response.status_code == 404, response.text
    assert b.dataset.name not in response.text
    assert b.chats.get(b.conversation.conversation_id)
    assert b.datasets.get(b.dataset.dataset_id)


def test_lists_names_schema_retrieval_and_repository_checks(accounts):
    a, b = accounts.a, accounts.b
    expected = ([None] if a.datasets.has_demo_data() else []) + [a.dataset.dataset_id]
    assert [item["dataset_id"] for item in a.client.get("/api/datasets").json()] == expected
    assert [item["conversation_id"] for item in a.client.get("/api/conversations").json()] == [
        str(a.conversation.conversation_id),
    ]
    assert a.dataset.name == b.dataset.name
    with pytest.raises(ResourceConflictError):
        a.datasets.create_workspace("sALes")
    with pytest.raises(ResourceNotFoundError):
        a.datasets.categorical_values(b.dataset)
    context = build_dataset_sql_context(a.dataset, a.datasets.categorical_values(a.dataset))
    validator = SqlValidator(context.table_columns, context.allowed_schemas, max_tables=1)
    with pytest.raises(SqlValidationError):
        validator.validate(f"SELECT * FROM uploaded_data.{b.dataset.table.physical_table_name}")
    vector = [1.0, *([0.0] * 767)]
    own = a.documents.retrieve(vector, dataset_id=a.dataset.dataset_id)
    assert own and "account 0" in own[0].content
    with pytest.raises(ResourceNotFoundError):
        a.documents.retrieve(vector, dataset_id=b.dataset.dataset_id)
    with pytest.raises(ResourceNotFoundError):
        a.documents.get_document(a.dataset.dataset_id, b.document.document_id)


def test_sessions_store_hash_rotate_expire_and_revoke(accounts):
    auth, engine, a = accounts.auth, accounts.engine, accounts.a
    assert auth.authenticate(a.raw).user_id == a.user_id
    with engine.connect() as connection:
        stored = (
            connection.execute(
                select(UserSession).where(UserSession.token_hash == token_hash(a.raw))
            )
            .mappings()
            .one()
        )
    assert a.raw not in str(stored)
    rotated = auth.create_session(a.user_id, 1, a.raw)
    with pytest.raises(HTTPException) as error:
        auth.authenticate(a.raw)
    assert error.value.status_code == 401
    auth.revoke(token_hash(rotated))
    with pytest.raises(HTTPException):
        auth.authenticate(rotated)
    expired = auth.create_session(a.user_id, 1)
    with engine.begin() as connection:
        connection.execute(
            update(UserSession)
            .where(UserSession.token_hash == token_hash(expired))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    with pytest.raises(HTTPException):
        auth.authenticate(expired)
    assert a.client.get("/api/auth/me").status_code == 401


def test_login_callback_browser_binding_replay_logout(accounts, monkeypatch):
    auth = accounts.auth
    authorize = AsyncMock(return_value={"url": "https://accounts.google.com/o/oauth2/auth"})
    monkeypatch.setattr(
        "app.auth.routes.google_client",
        lambda settings: SimpleNamespace(
            create_authorization_url=authorize,
        ),
    )
    identity = AsyncMock(
        return_value=(
            "login-fixture-" + uuid4().hex,
            accounts.a.client.get("/api/auth/me").json()["user"]["email"],
            "Login fixture",
        )
    )
    monkeypatch.setattr("app.auth.routes.verified_identity", identity)
    client = TestClient(app, follow_redirects=False)
    start = client.get("/api/auth/login")
    assert start.status_code == 302
    options = authorize.call_args.kwargs
    assert options["redirect_uri"] == accounts.settings.oidc_callback_url
    assert options["nonce"] and len(options["code_verifier"]) >= 43
    callback = "/api/auth/callback?code=fixture&state=" + options["state"]
    assert TestClient(app).get(callback).status_code == 400
    assert client.get(callback.replace(options["state"], "wrong-state")).status_code == 400
    result = client.get(callback)
    assert result.status_code == 303
    assert (
        "HttpOnly" in result.headers["set-cookie"]
        and "SameSite=lax" in result.headers["set-cookie"]
    )
    assert client.get(callback).status_code == 400
    assert identity.await_count == 1
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    csrf = me.json()["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 403
    assert (
        client.post(
            "/api/auth/logout",
            headers={
                "Origin": accounts.settings.app_origin,
                "X-CSRF-Token": csrf,
            },
        ).status_code
        == 204
    )
    assert client.get("/api/auth/me").status_code == 401
    raw = "expired-browser-binding-" + uuid4().hex
    auth.save_flow(raw, "s", "n", "v")
    assert auth.consume_flow(raw, "s") == ("n", "v")
    with pytest.raises(HTTPException):
        auth.consume_flow(raw, "s")


def test_shared_demo_conversations_stay_private(accounts, monkeypatch):
    from tests.test_management_api import FakeChatService

    monkeypatch.setattr("app.api.routes.build_chat_service", lambda settings: FakeChatService())
    a, b = accounts.a, accounts.b
    created = a.client.post("/api/conversations", json={}).json()
    path = f"/api/conversations/{created['conversation_id']}"
    content_hash = uuid4().hex + uuid4().hex
    with accounts.engine.begin() as connection:
        connection.execute(
            insert(DocumentChunk).values(
                source_file="synthetic-demo.md",
                section_title="Test",
                content="Synthetic demo",
                content_hash=content_hash,
                embedding=[1.0, *([0.0] * 767)],
            )
        )
    try:
        response = a.client.post(path + "/messages", json={"message": "Count demo products"})
        assert (
            response.status_code == 200
            and response.json()["assistant_message"]["response"]["error"] is None
        )
    finally:
        with accounts.engine.begin() as connection:
            connection.execute(
                delete(DocumentChunk).where(DocumentChunk.content_hash == content_hash)
            )
    assert b.client.get(path).status_code == 404
    assert len(a.chats.get(created["conversation_id"]).messages) == 2


def test_beta_rate_concurrency_and_storage_limits(accounts):
    settings = accounts.settings.model_copy(
        update={
            "beta_chat_per_user_hour": 1,
            "beta_system_concurrency": 1,
            "beta_user_concurrency": 1,
        }
    )
    control = ResourceControl(accounts.engine, settings)
    with (
        control.work(accounts.a.user_id, "chat"),
        pytest.raises(HTTPException) as error,
        control.work(accounts.b.user_id, "chat"),
    ):
        pytest.fail("System concurrency exceeded")
    assert error.value.status_code == 429
    with pytest.raises(HTTPException), control.work(accounts.a.user_id, "chat"):
        pytest.fail("Per-user rate exceeded")
    control = ResourceControl(
        accounts.engine, settings.model_copy(update={"beta_max_user_bytes": 1024})
    )
    with pytest.raises(HTTPException) as error:
        control.storage(accounts.a.user_id)
    assert error.value.status_code == 429


@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize("route", ["SQL", "RAG", "HYBRID"])
def test_owned_pipelines_execute_real_sql_retrieval_with_offline_providers(
    accounts,
    monkeypatch,
    model,
    route,
):
    requested, embeddings, prompts = [], [], []
    table = accounts.a.dataset.table.physical_table_name

    class Gateway:
        def generate_structured(self, prompt, response_model):
            prompts.append(prompt)
            assert "Private account 1" not in prompt
            assert accounts.b.dataset.table.physical_table_name not in prompt
            if response_model.__name__ == "RouteDecision":
                return response_model(route=route, reason="Offline fixture")
            if response_model.__name__ == "SqlDraft":
                return response_model(
                    sql=f"SELECT SUM(value) AS total, COUNT(*) AS matched_row_count "
                    f"FROM uploaded_data.{table}"
                )
            ids = [int(value) for value in re.findall(r"chunk_id=(\d+)", prompt)]
            assert ids
            return response_model(answer="Only the current account evidence.", used_chunk_ids=ids)

        def generate_text(self, prompt):
            prompts.append(prompt)
            return "Total is 100."

        def close(self):
            pass

    monkeypatch.setattr(
        "app.ai.chat.build_generation_gateway",
        lambda settings, model_id: requested.append(model_id) or Gateway(),
    )
    monkeypatch.setattr(
        "app.dependencies.build_embedding_gateway",
        lambda settings: SimpleNamespace(
            embed_query=lambda question: embeddings.append(question) or [1.0, *([0.0] * 767)],
        ),
    )
    response = accounts.a.client.post(
        "/api/chat",
        json={
            "message": f"{route} question",
            "dataset_id": accounts.a.dataset.dataset_id,
            "model_id": model,
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["error"] is None and result["route"] == route
    assert result["requested_model"] == result["used_model"] == model
    assert result["fallback_used"] is False and requested == [model]
    assert len(embeddings) == (0 if route == "SQL" else 1)
    if route != "RAG":
        assert result["rows"] == [{"total": "100", "matched_row_count": 1}]
    if route != "SQL":
        assert result["sources"] and all(
            "account 0" in source["content"] for source in result["sources"]
        )


def test_authenticated_preview_budget_is_separate_and_limits_require_login(accounts):
    accounts.settings.beta_preview_per_user_hour = 2
    accounts.settings.beta_upload_per_user_hour = 1
    client = accounts.a.client
    caps = client.get("/api/uploads/limits")
    assert caps.status_code == 200
    assert caps.json()["max_rows"] == accounts.settings.upload_max_rows
    assert caps.json()["preview_per_hour"] == 2
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/uploads/limits").status_code == 401
    path = f"/api/datasets/{accounts.a.dataset.dataset_id}/tables"
    for _ in range(2):
        assert (
            client.post(path + "/preview", files={"file": ("extra.csv", b"Fee\n100\n")}).status_code
            == 200
        )
    denied = client.post(path + "/preview", files={"file": ("extra.csv", b"Fee\n100\n")})
    assert denied.status_code == 429
    assert 1 <= int(denied.headers["Retry-After"]) <= 3600
    added = client.post(path + "/import", files={"file": ("extra.csv", b"Fee\n100\n")})
    assert added.status_code == 201
    assert added.json()["table_count"] == 2
    assert (
        client.post(path + "/import", files={"file": ("more.csv", b"Fee\n100\n")}).status_code
        == 429
    )


@pytest.mark.parametrize("extension", ["pdf", "docx", "txt", "md"])
def test_document_provider_gate_is_explicit_and_does_not_persist(accounts, monkeypatch, extension):
    from unittest.mock import Mock

    from tests.test_document_upload_parser import _docx_bytes, _pdf_bytes

    accounts.settings.beta_provider_data_enabled = False
    provider = Mock(side_effect=AssertionError("Provider must not be initialized"))
    monkeypatch.setattr("app.api.routes.GeminiGateway", provider)
    content = {
        "pdf": _pdf_bytes("Synthetic rules"),
        "docx": _docx_bytes("Synthetic rules"),
        "txt": b"Synthetic rules",
        "md": b"# Rules\n\nSynthetic rules",
    }[extension]
    before = len(accounts.a.documents.list_documents(accounts.a.dataset.dataset_id))
    response = accounts.a.client.post(
        f"/api/datasets/{accounts.a.dataset.dataset_id}/documents",
        files={"file": (f"blocked.{extension}", content)},
    )
    assert response.status_code == 403
    assert "chưa cho phép" in response.json()["detail"]
    assert len(accounts.a.documents.list_documents(accounts.a.dataset.dataset_id)) == before
    assert accounts.a.client.get("/api/uploads/limits").json()["provider_data_enabled"] is False
    assert accounts.a.client.get("/api/models").json()["ai_enabled"] is False
    provider.assert_not_called()


def test_storage_limit_rolls_back_new_table_and_metadata(accounts, monkeypatch):
    from app.core.config import Settings
    from app.database.integrity import legacy_fingerprints

    before = legacy_fingerprints(accounts.engine)
    monkeypatch.setattr(
        "app.database.quotas.get_settings",
        lambda: Settings(
            _env_file=None,
            beta_max_user_bytes=1024,
        ),
    )
    with pytest.raises(HTTPException) as error:
        accounts.a.datasets.add_table(
            accounts.a.dataset.dataset_id,
            parse_tabular_file(
                "extra.csv",
                b"Value\n10\n",
                max_bytes=1000,
                max_rows=10,
                max_columns=10,
            ),
            "Extra",
        )
    assert error.value.status_code == 429
    assert before == legacy_fingerprints(accounts.engine)


def test_inactive_and_uninvited_accounts_lose_access(accounts, monkeypatch):
    a = accounts.a
    with accounts.engine.begin() as connection:
        connection.execute(update(User).where(User.user_id == a.user_id).values(active=False))
    assert a.client.get("/api/auth/me").status_code == 401
    with accounts.engine.begin() as connection:
        connection.execute(update(User).where(User.user_id == a.user_id).values(active=True))
    settings = accounts.settings.model_copy(update={"auth_invited_emails": []})
    monkeypatch.setattr("app.auth.dependencies.get_settings", lambda: settings)
    response = a.client.get("/api/datasets")
    assert response.status_code == 403 and response.headers["X-Session-Invalid"] == "1"


def test_expired_oidc_flow_rejected_and_reader_cannot_read_auth_tables(accounts):
    from sqlalchemy.exc import DBAPIError

    raw = "expired-" + uuid4().hex
    accounts.auth.save_flow(raw, "state", "nonce", "verifier")
    with accounts.engine.begin() as connection:
        connection.execute(
            update(OidcFlow)
            .where(OidcFlow.token_hash == token_hash(raw))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    with pytest.raises(HTTPException) as error:
        accounts.auth.consume_flow(raw, "state")
    assert error.value.status_code == 400
    for table in ("users", "user_sessions", "oidc_flows", "resource_limits", "resource_leases"):
        with get_readonly_engine().connect() as connection, pytest.raises(DBAPIError):
            connection.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
