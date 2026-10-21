"""Gate D questions and data replayed offline; drafts are explicit hypotheses, not live evidence."""

import json
import re
from decimal import Decimal

import pytest
from pydantic import BaseModel
from sqlalchemy import text

from app.core.diagnostics import diagnostic_request
from app.database.session import get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm, RelationshipInput
from app.dependencies import build_workspace_context
from app.rag.upload_parser import parse_document_file
from app.routing.hybrid import HybridAnswerDraft
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.generator import SqlDraft
from tests.gate_d_fixture import POLICY, QUESTIONS, uploads
from tests.test_auth_integration import accounts  # noqa: F401
from tests.test_dataset_parser import parse
from tests.test_guest_integration import OfflineEmbedder

pytestmark = pytest.mark.integration


@pytest.fixture
def gate_d_workspace(accounts, monkeypatch):  # noqa: F811
    a = accounts.a
    accounts.settings.sql_join_v1_enabled = True
    files, facts = uploads()
    dataset = a.datasets.create_workspace("Gate D offline synthetic")
    try:
        for filename, content in files:
            dataset = a.datasets.add_table(
                dataset.dataset_id, parse(filename, content), auto_relationships=True
            )
        relations = RelationshipRepository(get_setup_engine(), a.user_id)
        warehouse, driver, _ = dataset.tables
        candidate = RelationshipInput(
            source_table_id=str(driver.dataset_table_id),
            source_column="kho_id",
            target_table_id=str(warehouse.dataset_table_id),
            target_column="kho_id",
        )
        preview = relations.preview(dataset.dataset_id, candidate)
        assert preview.valid
        relations.confirm(
            dataset.dataset_id,
            RelationshipConfirm(
                **candidate.model_dump(), revision=preview.revision, confirmed=True
            ),
        )
        records = relations.list(dataset.dataset_id)
        assert len(records) == 2 and {r.origin for r in records} == {"automatic", "manual"}
        embedder = OfflineEmbedder()
        monkeypatch.setattr("app.dependencies.build_embedding_gateway", lambda _: embedder)
        yield accounts, dataset, facts, embedder
    finally:
        a.datasets.delete(dataset.dataset_id, delete_conversations=True)


def independent_oracle(facts: list[dict], level: str) -> list[dict]:
    values, parameters = [], {}
    for i, row in enumerate(facts):
        parameters.update({f"{key}{i}": value for key, value in row.items()})
        values.append("(" + ",".join(f":{key}{i}" for key in row) + ")")
    columns = ",".join(facts[0])
    if level == "1":
        query = "SELECT don_id,phi_giao_vnd::numeric::text AS phi_giao_vnd,trang_thai "
        suffix = "ORDER BY don_id"
    else:
        key, label = ("tai_xe_id", "ten_tai_xe") if level == "2" else ("kho_id", "ten_kho")
        query = (
            f"SELECT {key},{label},SUM(phi_giao_vnd::numeric)::text AS total,"
            "COUNT(*) AS fact_row_count "
        )
        suffix = f"GROUP BY {key},{label} ORDER BY fact_row_count DESC,{key}"
    with get_setup_engine().connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                text(query + f"FROM (VALUES {','.join(values)}) known({columns}) " + suffix),
                parameters,
            ).mappings()
        ]


def draft_sql(dataset, level: str) -> str:
    warehouse, driver, fact = (t.physical_table_name for t in dataset.tables)
    if level == "1":
        return f"SELECT don_id,phi_giao_vnd,trang_thai FROM uploaded_data.{fact} ORDER BY don_id"
    key, label = ("d.tai_xe_id", "d.ten_tai_xe") if level == "2" else ("k.kho_id", "k.ten_kho")
    bindings = (
        f"FROM uploaded_data.{fact} f INNER JOIN uploaded_data.{driver} d "
        "ON f.tai_xe_id=d.tai_xe_id "
    )
    if level != "2":
        bindings += f"INNER JOIN uploaded_data.{warehouse} k ON d.kho_id=k.kho_id "
    return (
        f"SELECT {key},{label},SUM(f.phi_giao_vnd) AS total,COUNT(*) AS fact_row_count "
        + bindings
        + f"GROUP BY {key},{label} ORDER BY COUNT(*) DESC,{key}"
    )


def add_policy(actors, dataset, embedder):
    actors.a.documents.add_document(
        dataset.dataset_id,
        parse_document_file("live_gate_d_kpi.md", POLICY.encode(), max_bytes=10000),
        embedder,
    )
    return actors.a.datasets.get(dataset.dataset_id)


@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize(
    "level,business_alias",
    [
        ("1", False),
        ("2", False),
        ("3", False),
        ("H", False),
        ("2", True),
        ("3", True),
        ("H", True),
    ],
)
def test_gate_d_questions_oracle_and_authenticated_history(
    gate_d_workspace, monkeypatch, model: str, level: str, business_alias: bool
) -> None:
    accounts, dataset, facts, embedder = gate_d_workspace  # noqa: F811
    expected = independent_oracle(facts, level)
    if business_alias:
        for row in expected:
            row["delivery_count"] = row.pop("fact_row_count")
    if level == "H":
        dataset = add_policy(accounts, dataset, embedder)
    context = build_workspace_context(accounts.settings, dataset, accounts.a.datasets)
    assert len(context.table_columns) == 3 and len(context.approved_joins) == 2
    assert context.has_documents is (level == "H")
    assert sum(r["phi_giao_vnd"] is None for r in facts) == 4
    assert sum(r["phi_giao_vnd"] == "0.00" for r in facts) == 3
    if level in {"3", "H"}:
        assert [r["total"] for r in expected] == [
            "393500.00",
            "598000.00",
            "502000.00",
            "439000.00",
            "540000.00",
        ]
    qualified = [
        r["kho_id"]
        for r in expected
        if level == "H" and r["total"] is not None and Decimal(r["total"]) >= Decimal("500000.00")
    ]
    calls: list[str] = []

    class Gateway:
        def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
            calls.append(schema.__name__)
            if schema is RouteDecision:
                assert "Required FROM/JOIN fragment" not in prompt
                return RouteDecision(
                    route=RouteLabel.HYBRID if level == "H" else RouteLabel.SQL,
                    reason="Scripted offline route, not model accuracy",
                )
            if schema is SqlDraft:
                assert QUESTIONS[level] in prompt
                assert all(name in prompt for name in context.table_columns)
                assert "Never invent a document threshold" in prompt
                sql = draft_sql(dataset, level)
                return SqlDraft(
                    sql=sql.replace("AS fact_row_count", "AS delivery_count")
                    if business_alias
                    else sql
                )
            assert schema is HybridAnswerDraft
            if business_alias:
                assert '"field": "delivery_count", "kind": "row_count"' in prompt
            ids = [int(value) for value in re.findall(r"\[chunk_id=(\d+)", prompt)]
            assert ids and "500000.00" in prompt
            assert json.dumps(expected, ensure_ascii=False) in prompt
            return HybridAnswerDraft(answer=json.dumps(qualified), used_chunk_ids=[ids[0]])

        def generate_text(self, prompt: str) -> str:
            calls.append("answer")
            assert json.dumps(expected, ensure_ascii=False) in prompt
            return json.dumps(expected, ensure_ascii=False)

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    created = accounts.a.client.post(
        "/api/conversations", json={"dataset_id": dataset.dataset_id, "model_id": model}
    )
    path = "/api/conversations/" + created.json()["conversation_id"]
    with diagnostic_request() as trace:
        result = accounts.a.client.post(
            path + "/messages", json={"message": QUESTIONS[level], "model_id": model}
        )
    assert result.status_code == 200, result.text
    response = result.json()["assistant_message"]["response"]
    assert response["error"] is None and response["route"] == ("HYBRID" if level == "H" else "SQL")
    assert response["rows"] == expected and response["used_model"] == model
    assert not response["fallback_used"]
    assert json.loads(response["answer"]) == (qualified if level == "H" else expected)
    assert trace.facts["execution_reached"] and trace.facts["sql_validated"]
    if level == "H":
        assert response["sources"][0]["source_file"] == "live_gate_d_kpi.md"
        assert qualified == ["KHO02", "KHO03", "KHO05"]
    before = list(calls)
    assert accounts.a.client.get(path).json()["messages"][-1]["response"] == response
    assert accounts.b.client.get(path).status_code == 404
    assert calls == before


@pytest.mark.parametrize(
    "mutation,code,reason",
    [
        ("star_alias", "join_aggregate", "count_wrong_argument_semantics"),
        ("column_alias", "join_aggregate", "count_wrong_argument_semantics"),
        ("nullable_row", "join_aggregate", "count_wrong_argument_semantics"),
        ("dimension_sum", "join_aggregate", "dimension_column"),
        ("grain", "join_grain", None),
        ("key", "join_key", None),
        ("unsupported", "generator_unsupported", None),
    ],
)
def test_gate_d_hypotheses_stay_fail_closed_before_retrieval(
    gate_d_workspace, monkeypatch, mutation: str, code: str, reason: str | None
) -> None:
    accounts, dataset, _, embedder = gate_d_workspace  # noqa: F811
    dataset = add_policy(accounts, dataset, embedder)
    sql = draft_sql(dataset, "H")
    if mutation == "star_alias":
        sql = sql.replace("AS fact_row_count", "AS fact_value_count")
    elif mutation == "column_alias":
        sql = sql.replace("COUNT(*)", "COUNT(f.phi_giao_vnd)").replace(
            "AS fact_row_count", "AS matched_row_count"
        )
    elif mutation == "nullable_row":
        sql = sql.replace("COUNT(*)", "COUNT(f.phi_giao_vnd)")
    elif mutation == "dimension_sum":
        sql = sql.replace("SUM(f.phi_giao_vnd)", "SUM(d.tham_nien_nam)")
    elif mutation == "grain":
        sql = sql.replace("k.kho_id,", "").replace(",k.kho_id", "")
    elif mutation == "key":
        sql = sql.replace("f.tai_xe_id=d.tai_xe_id", "f.don_id=d.tai_xe_id")
    calls: list[str] = []

    class Gateway:
        def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
            calls.append(schema.__name__)
            if schema is RouteDecision:
                return RouteDecision(route=RouteLabel.HYBRID, reason="Offline hypothesis")
            assert schema is SqlDraft
            return (
                SqlDraft(sql="", unsupported_reason="Private synthetic hypothesis")
                if mutation == "unsupported"
                else SqlDraft(sql=sql)
            )

        def generate_text(self, prompt: str) -> str:
            pytest.fail("No grounding is allowed after an invalid draft")

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    created = accounts.a.client.post("/api/conversations", json={"dataset_id": dataset.dataset_id})
    path = "/api/conversations/" + created.json()["conversation_id"]
    with diagnostic_request() as trace:
        result = accounts.a.client.post(path + "/messages", json={"message": QUESTIONS["H"]})
    response = result.json()["assistant_message"]["response"]
    assert (
        response["route"] == "UNSUPPORTED" and response["rows"] == [] and response["sources"] == []
    )
    assert calls == ["RouteDecision", "SqlDraft"]
    assert not trace.facts["execution_reached"]
    assert not any(e["stage"] == "document_retrieval" for e in trace.events)
    assert any(
        e["stage"] == code and (reason is None or e["reason"] == reason) for e in trace.events
    )
    assert "Private synthetic" not in response["answer"]
