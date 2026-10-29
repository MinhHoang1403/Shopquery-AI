"""Automatic relationships use owner-locked uploads and the real execution guard."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import ResourceConflictError, ResourceNotFoundError
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipConfirm
from app.datasets.repository import DatasetRepository
from app.dependencies import build_workspace_context
from app.routing.router import RouteLabel
from app.semantic.wire import TaskProposal
from tests.auth_helpers import TEST_OWNER
from tests.plan_fixtures import decision_from_sql
from tests.semantic_fixtures import (
    proposal_for_evidence,
    proposal_from_plan,
)
from tests.test_auth_integration import accounts  # noqa: F401
from tests.test_dataset_parser import parse

pytestmark = pytest.mark.integration


@pytest.fixture
def workspace():
    repo = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repo.create_workspace("Automatic relationship " + uuid4().hex)
    try:
        yield repo, dataset.dataset_id, RelationshipRepository(get_setup_engine(), TEST_OWNER)
    finally:
        repo.delete(dataset.dataset_id, delete_conversations=True)


@pytest.mark.parametrize("reverse_upload", [False, True])
@pytest.mark.parametrize("entity", ["student", "customer", "employee"])
def test_upload_verifies_n_to_one_and_preserves_provenance(workspace, reverse_upload, entity):
    repo, dataset_id, relations = workspace
    tables = [
        parse(entity + "s.csv", f"{entity}_id,Name\nS1,An\nS2,Binh\n".encode()),
        parse("events.csv", f"{entity}_id,Amount\nS1,20.00\nS1,0.00\nS2,\n".encode()),
    ]
    for table in reversed(tables) if reverse_upload else tables:
        dataset = repo.add_table(dataset_id, table, auto_relationships=True)
    records = relations.list(dataset_id)
    assert len(records) == 1
    record = records[0]
    assert record.origin == "automatic" and not record.confirmed
    assert record.valid and record.cardinality == "many-to-one"
    context = build_workspace_context(
        get_settings().model_copy(update={"sql_join_v1_enabled": True}),
        dataset,
        repo,
    )
    assert len(context.approved_joins) == 1 and "Never JOIN tables" not in context.schema_context
    assert (record.source_rows, record.target_rows, record.orphan_rows) == (3, 2, 0)
    # Manual confirmation promotes provenance without duplicating the relationship.
    manual = relations.confirm(
        dataset_id,
        RelationshipConfirm(
            **record.model_dump(
                include={
                    "source_table_id",
                    "source_column",
                    "target_table_id",
                    "target_column",
                    "revision",
                }
            ),
            confirmed=True,
        ),
    )
    assert manual.confirmed and manual.origin == "manual"
    assert manual.relationship_id == record.relationship_id
    relations.delete(dataset_id, UUID(manual.relationship_id))
    repo.add_table(dataset_id, parse("notes.csv", b"Note\nHello\n"), auto_relationships=True)
    assert relations.approved(dataset_id) == ()


@pytest.mark.parametrize(
    "dimension,fact",
    [
        (b"Student id\nS1\nS1\n", b"Student id\nS1\nS1\n"),
        (b"Student id\nS1\nS2\n", b"Student id\nS1\nS3\nS1\n"),
        (b"Student id\nS1\nS2\n", b"Student id,Amount\nS1,1\n,2\nS1,3\n"),
        (b"Student id,Name\nS1,An\n,Binh\n", b"Student id\nS1\nS1\n"),
        (b"Student id\n101\n102\n", b"Student id\nS1\nS1\n"),
        (b"Student id\nS1\nS2\n", b"Student id\nS1\nS2\n"),
        (b"Id,Student id\nS1,S1\nS2,S2\n", b"Student id\nS1\nS1\nS2\n"),
        (b"Id\n101\n102\n", b"Id\n101\n101\n102\n"),
    ],
)
def test_ambiguous_unsafe_or_one_to_one_uploads_stay_manual(workspace, dimension, fact):
    repo, dataset_id, relations = workspace
    for name, content in (("students.csv", dimension), ("payments.csv", fact)):
        repo.add_table(dataset_id, parse(name, content), auto_relationships=True)
    assert relations.list(dataset_id) == []
    assert repo.get(dataset_id).table_count == 2


def test_flag_off_owner_isolation_and_atomic_failure(workspace, monkeypatch):
    repo, dataset_id, relations = workspace
    repo.add_table(dataset_id, parse("students.csv", b"Student id\nS1\nS2\n"))
    payments = parse("payments.csv", b"Student id,Amount\nS1,20\nS1,30\nS2,0\n")
    foreign = DatasetRepository(get_setup_engine(), get_readonly_engine(), uuid4())
    with pytest.raises(ResourceNotFoundError):
        foreign.add_table(dataset_id, payments, auto_relationships=True)
    assert repo.get(dataset_id).table_count == 1

    def fail(*args):
        raise ResourceConflictError("Synthetic verification timeout")

    with monkeypatch.context() as scoped:
        scoped.setattr(RelationshipRepository, "detect_on_upload", fail)
        with pytest.raises(ResourceConflictError):
            repo.add_table(dataset_id, payments, auto_relationships=True)
    assert repo.get(dataset_id).table_count == 1 and relations.list(dataset_id) == []
    repo.add_table(dataset_id, payments, auto_relationships=False)
    assert relations.list(dataset_id) == []


@pytest.mark.parametrize("model", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("reverse_join", [False, True])
def test_upload_chat_and_history_with_automatic_relation(
    accounts,  # noqa: F811
    monkeypatch,
    model,
    reverse_join,
):
    a = accounts.a
    accounts.settings.sql_join_v1_enabled = True
    monkeypatch.setattr("app.api.relationship_routes.get_settings", lambda: accounts.settings)
    dataset = a.datasets.create_workspace("Automatic API " + uuid4().hex)
    path = f"/api/datasets/{dataset.dataset_id}"
    contents = [
        ("students.csv", b"Student id,Student name\nS1,An\nS2,Binh\n"),
        ("payments.csv", b"Payment id,Student id,Amount paid\np1,S1,20.00\np2,S1,0.00\np3,S2,\n"),
    ]
    for name, content in contents:
        assert (
            a.client.post(
                path + "/tables/import",
                files={"file": (name, content)},
                headers={"X-CSRF-Token": "bad"},
            ).status_code
            == 403
        )
        result = a.client.post(path + "/tables/import", files={"file": (name, content)})
        assert result.status_code == 201, result.text
    records = a.client.get(path + "/relationships").json()["relationships"]
    assert len(records) == 1 and records[0]["origin"] == "automatic"
    assert records[0]["confirmed"] is False
    assert accounts.b.client.get(path + "/relationships").status_code == 404
    dataset = a.datasets.get(dataset.dataset_id)
    dimension, fact = dataset.tables
    bindings = (
        f"FROM uploaded_data.{dimension.physical_table_name} d INNER JOIN "
        f"uploaded_data.{fact.physical_table_name} f"
        if reverse_join
        else f"FROM uploaded_data.{fact.physical_table_name} f INNER JOIN "
        f"uploaded_data.{dimension.physical_table_name} d"
    )
    sql = (
        "SELECT d.student_id, d.student_name, SUM(f.amount_paid) AS total, "
        f"COUNT(f.student_id) AS fact_row_count {bindings} ON f.student_id=d.student_id "
        "GROUP BY d.student_id,d.student_name ORDER BY d.student_id"
    )
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            assert "Never JOIN tables" not in prompt
            if schema is TaskProposal:
                _task_route = RouteLabel.SQL
                if _task_route in {RouteLabel.RAG, RouteLabel.UNSUPPORTED}:
                    return proposal_for_evidence(
                        "documents" if _task_route == RouteLabel.RAG else "unavailable"
                    )
                _task_operation = "combine" if _task_route == RouteLabel.HYBRID else "query"
            assert schema is TaskProposal
            assert "row_count" in prompt and "non_null_count" in prompt
            assert '"name": "amount_paid"' in prompt
            assert "row_count" in prompt and "TaskProposal" in prompt
            return proposal_from_plan(decision_from_sql(sql, prompt), _task_operation)

        def generate_text(self, prompt):
            raise AssertionError("SQL presentation must not call a generation provider")

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    conversation = a.chats.create(dataset.dataset_id, model)
    response = a.client.post(
        f"/api/conversations/{conversation.conversation_id}/messages",
        json={"message": "Tên sinh viên, tổng tiền và số lần thanh toán", "model_id": model},
    )
    assert response.status_code == 200, response.text
    response = response.json()["assistant_message"]["response"]
    assert response["route"] == "SQL" and response["used_model"] == model
    assert response["fallback_used"] is False and not response["error"]
    assert calls == ["TaskProposal"]
    assert response["rows"] == [
        {"student_id": "S1", "student_name": "An", "total": "20.00", "fact_row_count": 2},
        {"student_id": "S2", "student_name": "Binh", "total": None, "fact_row_count": 1},
    ]
    assert "2 nhóm kết quả" in response["answer"]
    assert {c["key"] for c in response["result_columns"] if c["numeric"]} == {
        "total",
        "fact_row_count",
    }
    with get_setup_engine().connect() as connection:
        oracle = connection.execute(
            text(
                f"SELECT student_id, SUM(amount_paid), COUNT(*) FROM uploaded_data."
                f"{fact.physical_table_name} GROUP BY student_id ORDER BY student_id"
            )
        ).all()
    assert [row[2] for row in oracle] == [2, 1]
    assert str(oracle[0][1]) == "20.00" and oracle[1][1] is None
    history = a.client.get(f"/api/conversations/{conversation.conversation_id}").json()
    assert history["messages"][-1]["response"] == response


def test_inner_key_count_equivalence_is_not_a_nullable_id_assumption():
    with get_setup_engine().connect() as connection:
        row = connection.execute(
            text("""
            SELECT COUNT(*) AS rows, COUNT(f.key) AS keys, COUNT(f.id) AS ids
            FROM (VALUES (NULL::bigint, 101), (NULL, 101), (NULL, 102), (NULL, NULL)) f(id,key)
            INNER JOIN (VALUES (101), (102), (NULL)) d(key) ON f.key=d.key
        """)
        ).one()
    assert tuple(row) == (3, 3, 0)
