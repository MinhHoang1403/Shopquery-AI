"""Real sessions, CSRF and two owners protect relationship mutations."""

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlglot import parse_one

from app.auth.limits import ResourceControl
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm, RelationshipInput
from app.main import app
from tests.hybrid_fixtures import explanation_draft
from tests.test_auth_integration import accounts as auth_accounts  # noqa: F401
from tests.test_dataset_parser import parse

pytestmark = pytest.mark.integration


@pytest.fixture
def relationship_accounts(auth_accounts, monkeypatch):  # noqa: F811
    accounts = auth_accounts
    settings = accounts.settings
    settings.sql_join_v1_enabled = True
    monkeypatch.setattr("app.api.relationship_routes.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.api.relationship_routes.resource_control",
        lambda: ResourceControl(accounts.engine, settings),
    )
    for account in (accounts.a, accounts.b):
        account.dataset = account.datasets.add_table(
            account.dataset.dataset_id,
            parse("fact.csv", b"Key,Amount\n100,2\n100,3\n")
            if account is accounts.a
            else parse("fact.csv", b"Key,Amount\n200,2\n200,3\n"),
        )
    return accounts


def request_for(account) -> dict:
    return {
        "source_table_id": str(account.dataset.tables[1].dataset_table_id),
        "source_column": "key",
        "target_table_id": str(account.dataset.tables[0].dataset_table_id),
        "target_column": "value",
    }


def path_for(account) -> str:
    return f"/api/datasets/{account.dataset.dataset_id}/relationships"


def test_authenticated_preview_confirm_delete_and_csrf(relationship_accounts):
    a = relationship_accounts.a
    path, body = path_for(a), request_for(a)
    preview = a.client.post(path + "/preview", json=body)
    assert preview.status_code == 200 and preview.json()["valid"]
    assert a.client.get(path).json()["relationships"] == []
    confirmation = {**body, "revision": preview.json()["revision"], "confirmed": True}
    for headers in ({"X-CSRF-Token": "invalid"}, {"Origin": "https://attacker.invalid"}):
        assert a.client.post(path, json=confirmation, headers=headers).status_code == 403
    with TestClient(app) as anonymous:
        assert anonymous.get(path).status_code == 401
    record = a.client.post(path, json=confirmation)
    assert record.status_code == 200
    assert a.client.post(path, json=confirmation).json() == record.json()
    relation_path = path + "/" + record.json()["relationship_id"]
    assert a.client.delete(relation_path).status_code == 409
    assert a.client.delete(relation_path + "?confirmed=true").status_code == 204
    assert a.client.get(path).json()["relationships"] == []
    assert a.datasets.get(a.dataset.dataset_id).table_count == 2
    assert a.chats.get(a.conversation.conversation_id)


@pytest.mark.parametrize("operation", ["list", "preview", "confirm", "delete", "foreign_table"])
def test_owner_a_cannot_use_b_relationships(relationship_accounts, operation):
    accounts = relationship_accounts
    a, b = accounts.a, accounts.b
    repo = RelationshipRepository(accounts.engine, b.user_id)
    body = request_for(b)
    preview = repo.preview(b.dataset.dataset_id, RelationshipInput(**body))
    confirmation = {**body, "revision": preview.revision, "confirmed": True}
    record = repo.confirm(b.dataset.dataset_id, RelationshipConfirm(**confirmation))
    path = path_for(b)
    if operation == "list":
        response = a.client.get(path)
    elif operation == "delete":
        response = a.client.delete(path + f"/{record.relationship_id}?confirmed=true")
    elif operation == "foreign_table":
        response = a.client.post(path_for(a) + "/preview", json=body)
    elif operation == "preview":
        response = a.client.post(path + "/preview", json=body)
    else:
        response = a.client.post(path, json=confirmation)
    assert response.status_code == 404
    assert len(repo.list(b.dataset.dataset_id)) == 1
    assert str(b.dataset.tables[0].physical_table_name) not in response.text


def test_extra_sql_physical_names_cross_workspace_and_flag_off(relationship_accounts, monkeypatch):
    accounts, a = relationship_accounts, relationship_accounts.a
    path, body = path_for(a), request_for(a)
    for extra in ({"sql": "DROP TABLE users"}, {"physical_table_name": "users"}):
        assert a.client.post(path + "/preview", json={**body, **extra}).status_code == 422
    other = a.datasets.create("Other workspace", parse("dim.csv", b"Id\n100\n"))
    assert (
        a.client.post(
            path + "/preview",
            json={
                **body,
                "target_table_id": str(other.table.dataset_table_id),
                "target_column": "id",
            },
        ).status_code
        == 404
    )
    off = accounts.settings.model_copy(update={"sql_join_v1_enabled": False})
    monkeypatch.setattr("app.api.relationship_routes.get_settings", lambda: off)
    assert a.client.get(path).json() == {"enabled": False, "relationships": []}
    assert a.client.post(path + "/preview", json=body).status_code == 403


@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize("pipeline", ["SQL", "RAG", "HYBRID"])
@pytest.mark.parametrize("reverse", [False, True])
def test_join_api_pipelines_and_persisted_history(
    relationship_accounts, monkeypatch, model, pipeline, reverse: bool
):
    from app.rag.pipeline import RagAnswerDraft
    from app.routing.hybrid import HybridAnswerDraft
    from app.routing.router import RouteDecision, RouteLabel
    from app.text_to_sql.query_plan import PlanDecision
    from tests.plan_fixtures import decision_from_sql
    from tests.test_guest_integration import OfflineEmbedder

    a = relationship_accounts.a
    chunk_id = a.documents.retrieve(
        OfflineEmbedder().embed_query("policy"), dataset_id=a.dataset.dataset_id
    )[0].chunk_id
    repo = RelationshipRepository(relationship_accounts.engine, a.user_id)
    body = RelationshipInput(**request_for(a))
    preview = repo.preview(a.dataset.dataset_id, body)
    repo.confirm(
        a.dataset.dataset_id,
        RelationshipConfirm(
            **body.model_dump(),
            revision=preview.revision,
            confirmed=True,
        ),
    )
    fact, dim = a.dataset.tables[1].physical_table_name, a.dataset.tables[0].physical_table_name
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            if schema is RouteDecision:
                assert fact in prompt and dim in prompt
                return RouteDecision(
                    policy_intent="none",
                    policy_scope="unspecified",
                    evidence_requirement={
                        "SQL": "tables",
                        "RAG": "documents",
                        "HYBRID": "both",
                        "UNSUPPORTED": "unavailable",
                    }[RouteLabel(pipeline)],
                    route=RouteLabel(pipeline),
                    reason="Offline JOIN test",
                )
            if schema is PlanDecision:
                bindings = (
                    f"FROM uploaded_data.{dim} d INNER JOIN uploaded_data.{fact} f"
                    if reverse
                    else f"FROM uploaded_data.{fact} f INNER JOIN uploaded_data.{dim} d"
                )
                return decision_from_sql(
                    f"SELECT SUM(f.amount) AS total {bindings} ON f.key=d.value", prompt
                )
            if schema is RagAnswerDraft:
                return RagAnswerDraft(answer="Synthetic policy", used_chunk_ids=[chunk_id])
            if schema is HybridAnswerDraft:
                return explanation_draft(prompt, [chunk_id])
            raise AssertionError(schema)

        def generate_text(self, prompt):
            raise AssertionError("Structured pipelines must not add a text generation call")

    selected = []

    def build(config, model_id):
        selected.append(model_id)
        return Gateway()

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", build)
    monkeypatch.setattr("app.dependencies.build_embedding_gateway", lambda _: OfflineEmbedder())
    created = a.client.post(
        "/api/conversations", json={"dataset_id": a.dataset.dataset_id, "model_id": model}
    )
    path = "/api/conversations/" + created.json()["conversation_id"]
    result = a.client.post(
        path + "/messages", json={"message": "Synthetic question", "model_id": model}
    )
    assert result.status_code == 200, result.text
    response = result.json()["assistant_message"]["response"]
    assert response["error"] is None and response["route"] == pipeline
    assert response["used_model"] == model and selected == [model]
    assert len(calls) == {"SQL": 2, "RAG": 2, "HYBRID": 3}[pipeline]
    if pipeline == "SQL":
        assert response["answer"] == "Trong phạm vi dữ liệu truy vấn, **Tổng Amount** là **5**."
        assert response["result_columns"] == [
            {
                "key": "total",
                "label": "Tổng Amount",
                "numeric": True,
                "data_type": "NUMERIC",
                "provenance": "aggregate",
                "aggregate": "sum",
                "source_label": "Amount",
            }
        ]
    if pipeline != "RAG":
        assert response["rows"] == [{"total": "5"}] and " JOIN " in response["sql"]
        root = parse_one(response["sql"], read="postgres")
        assert root.args["from_"].this.name == fact
        assert root.args["joins"][0].this.name == dim
    if pipeline != "SQL":
        assert response["sources"][0]["source_file"] == "policy.md"
    detail = a.client.get(path).json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][-1]["response"] == response


@pytest.mark.parametrize("pipeline", ["SQL", "RAG", "HYBRID"])
def test_invalid_sql_or_citation_never_persists_invented_success(
    relationship_accounts, monkeypatch, pipeline: str
) -> None:
    from app.rag.pipeline import RagAnswerDraft
    from app.routing.hybrid import HybridAnswerDraft
    from app.routing.router import RouteDecision, RouteLabel
    from app.text_to_sql.query_plan import PlanDecision
    from tests.plan_fixtures import decision_from_sql
    from tests.test_guest_integration import OfflineEmbedder

    a = relationship_accounts.a
    fact = a.dataset.tables[1].physical_table_name

    class Gateway:
        def generate_structured(self, prompt, schema):
            if schema is RouteDecision:
                return RouteDecision(
                    policy_intent="none",
                    policy_scope="unspecified",
                    evidence_requirement={
                        "SQL": "tables",
                        "RAG": "documents",
                        "HYBRID": "both",
                        "UNSUPPORTED": "unavailable",
                    }[RouteLabel(pipeline)],
                    route=RouteLabel(pipeline),
                    reason="Negative synthetic case",
                )
            if schema is PlanDecision:
                return decision_from_sql(
                    "SELECT * FROM public.users"
                    if pipeline == "SQL"
                    else f"SELECT SUM(amount) AS total FROM uploaded_data.{fact}",
                    prompt,
                )
            if schema is RagAnswerDraft:
                return RagAnswerDraft(
                    answer="Must not be persisted as success", used_chunk_ids=[-1]
                )
            if schema is HybridAnswerDraft:
                return explanation_draft(prompt, [-1])
            raise AssertionError(schema)

        def generate_text(self, prompt):
            assert pipeline == "HYBRID"
            return "Synthetic total 5"

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    monkeypatch.setattr("app.dependencies.build_embedding_gateway", lambda _: OfflineEmbedder())
    created = a.client.post("/api/conversations", json={"dataset_id": a.dataset.dataset_id})
    path = "/api/conversations/" + created.json()["conversation_id"]
    sent = a.client.post(path + "/messages", json={"message": "Synthetic negative"})
    assert sent.status_code == 200
    response = sent.json()["assistant_message"]["response"]
    assert response["error"]
    assert response["sql"] is None and response["rows"] == [] and response["sources"] == []
    assert "Must not be persisted as success" not in sent.text
    assert a.client.get(path).json()["messages"][-1]["response"] == response


@pytest.mark.parametrize("model", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("route", ["SQL", "HYBRID"])
def test_aggregate_subreason_is_logged_but_not_exposed_or_persisted(
    relationship_accounts, monkeypatch, caplog, model: str, route: str
) -> None:
    from app.routing.router import RouteDecision, RouteLabel
    from app.text_to_sql.query_plan import PlanDecision

    a = relationship_accounts.a
    relations = RelationshipRepository(relationship_accounts.engine, a.user_id)
    body = RelationshipInput(**request_for(a))
    preview = relations.preview(a.dataset.dataset_id, body)
    relations.confirm(
        a.dataset.dataset_id,
        RelationshipConfirm(
            **body.model_dump(),
            revision=preview.revision,
            confirmed=True,
        ),
    )
    dim, fact = a.dataset.tables[0].physical_table_name, a.dataset.tables[1].physical_table_name
    sql = (
        f"SELECT COUNT(*) AS fact_value_count FROM uploaded_data.{dim} d "
        f"INNER JOIN uploaded_data.{fact} f ON f.key=d.value"
    )
    gateway, embedder = Mock(), Mock()
    embedder.embed_query.return_value = [1.0] + [0.0] * 767

    def structured(prompt, schema):
        from app.text_to_sql.query_plan import PlanField, QueryPlan

        if schema is RouteDecision:
            return RouteDecision(
                policy_intent="none",
                policy_scope="unspecified",
                evidence_requirement={
                    "SQL": "tables",
                    "RAG": "documents",
                    "HYBRID": "both",
                    "UNSUPPORTED": "unavailable",
                }[RouteLabel(route)],
                route=RouteLabel(route),
                reason="Synthetic aggregate refusal",
            )
        assert schema is PlanDecision
        catalog = json.JSONDecoder().raw_decode(prompt.split("Authorized catalog JSON:\n")[1])[0]
        source = next(table["id"] for table in catalog["tables"] if table["name"] == fact)
        return PlanDecision(
            plan=QueryPlan(
                source=source,
                fields=[PlanField(alias="fact_value_count", aggregate="row_count")],
                relationships=[relation["id"] for relation in catalog["relationships"]],
            )
        )

    gateway.generate_structured.side_effect = structured
    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: gateway)
    monkeypatch.setattr("app.dependencies.build_embedding_gateway", lambda _: embedder)
    created = a.client.post(
        "/api/conversations", json={"dataset_id": a.dataset.dataset_id, "model_id": model}
    )
    assert created.status_code == 201
    path = "/api/conversations/" + created.json()["conversation_id"]
    with caplog.at_level("INFO", logger="app.routing.service"):
        sent = a.client.post(
            path + "/messages", json={"message": "Synthetic count", "model_id": model}
        )
    assert sent.status_code == 200
    response = sent.json()["assistant_message"]["response"]
    assert response["route"] == "UNSUPPORTED" and response["error"] is None
    assert response["used_model"] == model and response["fallback_used"] is False
    assert response["sql"] is None and response["rows"] == [] and response["sources"] == []
    history = a.client.get(path)
    assert history.status_code == 200
    assert history.json()["messages"][-1]["response"] == response
    assert "join_aggregate (count_wrong_argument_semantics)" in caplog.text
    for private in (sql, dim, fact):
        assert private not in caplog.text
    for private in (
        sql,
        dim,
        fact,
        "join_aggregate",
        "aggregate_reason",
        "count_wrong_argument_semantics",
    ):
        assert private not in sent.text and private not in history.text
    assert gateway.generate_structured.call_count == 2
    gateway.generate_text.assert_not_called()
    if route == "HYBRID":
        embedder.embed_query.assert_called_once_with("Synthetic count")
    else:
        embedder.embed_query.assert_not_called()
