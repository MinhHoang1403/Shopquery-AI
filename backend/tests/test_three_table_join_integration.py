"""Real guarded three-table SQL, owner-scoped API/history and isolated Guest TEMP."""

from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Event
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import ResourceConflictError, SqlUnsupportedError
from app.database.guest_access import configure_guest_access
from app.database.integrity import legacy_fingerprints
from app.database.session import get_readonly_engine, get_setup_engine
from app.datasets.relationship_detection import detect_relationships
from app.datasets.relationship_repository import RelationshipRepository
from app.datasets.relationships import RelationshipRecord
from app.datasets.repository import DatasetRepository
from app.dependencies import build_workspace_context
from app.guest.pipeline import GuestSqlDatabase, run_guest_chat
from app.guest.store import GuestStore
from app.guest.worker import parse_guest_file
from app.rag.pipeline import RagAnswerDraft
from app.rag.upload_parser import parse_document_file
from app.routing.hybrid import HybridAnswerDraft
from app.routing.router import RouteLabel
from app.semantic.wire import TaskProposal
from app.text_to_sql.executor import SqlExecutor
from app.text_to_sql.validator import SqlValidator
from tests.auth_helpers import TEST_OWNER
from tests.hybrid_fixtures import explanation_draft
from tests.plan_fixtures import decision_from_sql
from tests.semantic_fixtures import (
    proposal_for_evidence,
    proposal_from_plan,
    scoped_dataset_service,
)
from tests.sql_validation_fixtures import ValidationPipeline
from tests.test_auth_integration import accounts  # noqa: F401
from tests.test_dataset_parser import parse
from tests.test_guest_integration import OfflineEmbedder

pytestmark = pytest.mark.integration
FILES = [
    ("courses.csv", b"Course id,Title,Fee\nC1,SQL,99.00\nC2,RAG,88.00\nC3,Math,77.00\n"),
    (
        "students.csv",
        b"Student id,Name,Course id\nS1,An,C1\nS2,Binh,C1\nS3,Chi,C2\nS4,Dung,C2\nS5,Em,C3\n",
    ),
    (
        "payments.csv",
        b"Payment id,Student id,Amount,Units\nP1,S1,20.00,9007199254740993\n"
        b"P2,S1,0.00,0\nP3,S2,0.00,1\nP4,S3,,2\nP5,S4,,3\n"
        b"P6,S5,12345678901234567890.12,4\nP7,S5,0.00,5\n",
    ),
]


def query(courses, students, payments, order=0, schema="uploaded_data"):
    c, s, p = (f"{schema}.{name}" for name in (courses, students, payments))
    bindings = [
        f"FROM {p} p INNER JOIN {s} s ON p.student_id=s.student_id "
        f"INNER JOIN {c} c ON s.course_id=c.course_id",
        f"FROM {s} s INNER JOIN {p} p ON p.student_id=s.student_id "
        f"INNER JOIN {c} c ON s.course_id=c.course_id",
        f"FROM {s} s INNER JOIN {c} c ON s.course_id=c.course_id "
        f"INNER JOIN {p} p ON p.student_id=s.student_id",
        f"FROM {c} c INNER JOIN {s} s ON s.course_id=c.course_id "
        f"INNER JOIN {p} p ON p.student_id=s.student_id",
    ]
    return (
        "SELECT c.course_id,c.title,SUM(p.amount) AS total,AVG(p.amount) AS average, "
        "COUNT(p.student_id) AS fact_row_count,COUNT(p.amount) AS fact_value_count "
        + bindings[order]
        + " GROUP BY c.course_id,c.title ORDER BY c.course_id"
    )


def scoped_validator(context):
    return SqlValidator(
        context.table_columns,
        context.allowed_schemas,
        max_tables=3,
        approved_joins=context.approved_joins,
        column_types=context.column_types,
        join_v1_enabled=True,
    )


@pytest.fixture
def workspace():
    repository = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repository.create_workspace("Three-table synthetic " + uuid4().hex)
    try:
        for name, content in FILES:
            dataset = repository.add_table(
                dataset.dataset_id, parse(name, content), auto_relationships=True
            )
        settings = get_settings().model_copy(update={"sql_join_v1_enabled": True})
        context = build_workspace_context(settings, dataset, repository)
        assert len(context.approved_joins) == 2
        yield repository, dataset, settings, context
    finally:
        repository.delete(dataset.dataset_id, delete_conversations=True)


@pytest.mark.parametrize("model", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("order", [0, 1, 2, 3])
def test_three_table_pipeline_keeps_exact_root_fact_oracle(workspace, monkeypatch, model, order):
    _, dataset, settings, context = workspace
    courses, students, payments = (t.physical_table_name for t in dataset.tables)
    sql = query(courses, students, payments, order)
    # No JOIN in the independent oracle: group known fixture fact keys into courses.
    with get_setup_engine().connect() as connection:
        oracle = (
            connection.execute(
                text(
                    "SELECT CASE student_id WHEN 'S1' THEN 'C1' WHEN 'S2' THEN 'C1' "
                    "WHEN 'S3' THEN 'C2' WHEN 'S4' THEN 'C2' ELSE 'C3' END AS course, "
                    "SUM(amount)::text AS total,AVG(amount)::text AS average,COUNT(*) AS n, "
                    "COUNT(amount) AS measured "
                    f"FROM uploaded_data.{payments} GROUP BY 1 ORDER BY 1"
                )
            )
            .mappings()
            .all()
        )
    calls = []

    class Gateway:
        def generate_structured(self, prompt, response_model):
            calls.append(response_model.__name__)
            assert (
                "Safe three-table tree" in prompt or '"relationships": [' in prompt
            ) and payments in prompt
            if response_model is TaskProposal:
                _task_route = RouteLabel.SQL
                if _task_route in {RouteLabel.RAG, RouteLabel.UNSUPPORTED}:
                    return proposal_for_evidence(
                        "documents" if _task_route == RouteLabel.RAG else "unavailable"
                    )
                _task_operation = "combine" if _task_route == RouteLabel.HYBRID else "query"
            assert response_model is TaskProposal
            assert "Use only approved N:1 edges" in prompt
            assert "one root fact" in prompt
            return proposal_from_plan(decision_from_sql(sql, prompt), _task_operation)

        def generate_text(self, prompt):
            calls.append("answer")
            assert '"total": null' in prompt and '"total": "20.00"' in prompt
            assert '"total": "12345678901234567890.12"' in prompt
            return "Synthetic result grounded in the rows"

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    response = scoped_dataset_service(
        settings.model_copy(update={"ai_default_model": model}),
        context,
    ).chat("Tổng thanh toán và số lần theo khóa học")
    assert response.route == RouteLabel.SQL and response.used_model == model
    assert not response.fallback_used and calls == ["TaskProposal"]
    assert response.sql.count("JOIN") == 2
    for row, expected in zip(response.rows, oracle, strict=True):
        assert row["course_id"] == expected.course
        assert (row["total"], row["average"], row["fact_row_count"], row["fact_value_count"]) == (
            expected.total,
            expected.average,
            expected.n,
            expected.measured,
        )
    validated = scoped_validator(context).validate(sql)
    assert validated.fact_table == payments and len(validated.relationship_ids) == 2
    assert scoped_validator(context).validate(validated.statement) == validated


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("mutation", ["delete", "metadata"])
def test_either_relation_revoked_or_stale_blocks_execution(workspace, index, mutation):
    _, dataset, _, context = workspace
    relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    edge = context.approved_joins[index]
    if mutation == "delete":
        relations.delete(dataset.dataset_id, UUID(edge.relationship_id))
    else:
        with get_setup_engine().begin() as connection:
            connection.execute(
                text(
                    "UPDATE dataset_tables SET row_count=row_count+1 "
                    "WHERE physical_table_name=:name"
                ),
                {"name": edge.target_table},
            )
    executor, gateway = Mock(), Mock()
    pipeline = ValidationPipeline(
        Mock(generate=Mock(return_value=query(*(t.physical_table_name for t in dataset.tables)))),
        scoped_validator(context),
        executor,
        gateway,
        execution_guard=partial(
            relations.execution_guard, dataset.dataset_id, context.approved_joins
        ),
    )
    with pytest.raises(ResourceConflictError):
        pipeline.run("Stale synthetic request")
    executor.execute.assert_not_called()
    gateway.generate_text.assert_not_called()


@pytest.mark.parametrize("index", [0, 1])
def test_guard_holds_both_relationships_against_concurrent_deletion(workspace, index):
    _, dataset, _, context = workspace
    relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    validated = scoped_validator(context).validate(
        query(*(t.physical_table_name for t in dataset.tables))
    )
    started = Event()

    def delete():
        started.set()
        relations.delete(dataset.dataset_id, UUID(context.approved_joins[index].relationship_id))

    with ThreadPoolExecutor(max_workers=1) as pool:
        with relations.execution_guard(dataset.dataset_id, context.approved_joins, validated):
            future = pool.submit(delete)
            assert started.wait(1)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.15)
        future.result(timeout=5)
    with (
        pytest.raises(ResourceConflictError),
        relations.execution_guard(
            dataset.dataset_id,
            context.approved_joins,
            validated,
        ),
    ):
        pytest.fail("Revoked second edge reached executor")


@pytest.mark.parametrize("model", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("route", ["SQL", "RAG", "HYBRID"])
def test_authenticated_upload_three_tables_pipeline_and_owner_history(
    accounts,  # noqa: F811
    monkeypatch,
    model,
    route,
):
    a, b = accounts.a, accounts.b
    accounts.settings.sql_join_v1_enabled = True
    monkeypatch.setattr("app.api.relationship_routes.get_settings", lambda: accounts.settings)
    dataset = a.datasets.create_workspace("Three-table API " + uuid4().hex)
    path = f"/api/datasets/{dataset.dataset_id}"
    for name, content in FILES:
        assert (
            a.client.post(
                path + "/tables/import",
                files={"file": (name, content)},
                headers={"X-CSRF-Token": "bad"},
            ).status_code
            == 403
        )
        assert (
            b.client.post(path + "/tables/import", files={"file": (name, content)}).status_code
            == 404
        )
        result = a.client.post(path + "/tables/import", files={"file": (name, content)})
        assert result.status_code == 201, result.text
    records = a.client.get(path + "/relationships").json()["relationships"]
    assert len(records) == 2 and all(r["origin"] == "automatic" for r in records)
    assert b.client.get(path + "/relationships").status_code == 404
    dataset = a.datasets.get(dataset.dataset_id)
    embedder = OfflineEmbedder()
    a.documents.add_document(
        dataset.dataset_id,
        parse_document_file(
            "rules.md",
            b"# Rule\n\nSynthetic threshold 40.",
            max_bytes=1000,
        ),
        embedder,
    )
    chunk = a.documents.retrieve(embedder.embed_query("rule"), dataset_id=dataset.dataset_id)[0]
    sql = query(*(t.physical_table_name for t in dataset.tables), order=3)
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            if schema is TaskProposal:
                _task_route = RouteLabel(route)
                if _task_route in {RouteLabel.RAG, RouteLabel.UNSUPPORTED}:
                    return proposal_for_evidence(
                        "documents" if _task_route == RouteLabel.RAG else "unavailable"
                    )
                _task_operation = "combine" if _task_route == RouteLabel.HYBRID else "query"
            if schema is TaskProposal:
                assert "Safe three-table tree" in prompt or '"relationships": [' in prompt
                return proposal_from_plan(decision_from_sql(sql, prompt), _task_operation)
            if schema is RagAnswerDraft:
                return RagAnswerDraft(
                    answer="Synthetic threshold 40", used_chunk_ids=[chunk.chunk_id]
                )
            if schema is HybridAnswerDraft:
                return explanation_draft(prompt, [chunk.chunk_id])
            raise AssertionError(schema)

        def generate_text(self, prompt):
            calls.append("answer")
            assert '"total": "20.00"' in prompt
            return "Synthetic SQL result"

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
    monkeypatch.setattr("app.dependencies.build_embedding_gateway", lambda _: embedder)
    created = a.client.post(
        "/api/conversations", json={"dataset_id": dataset.dataset_id, "model_id": model}
    )
    chat_path = "/api/conversations/" + created.json()["conversation_id"]
    result = a.client.post(
        chat_path + "/messages", json={"message": "Synthetic course analysis", "model_id": model}
    )
    assert result.status_code == 200, result.text
    response = result.json()["assistant_message"]["response"]
    assert response["route"] == route and response["error"] is None
    assert response["used_model"] == model and response["fallback_used"] is False
    assert len(calls) == {"SQL": 1, "RAG": 2, "HYBRID": 1}[route]
    if route != "RAG":
        assert response["sql"].count("JOIN") == 2
        assert [r["fact_row_count"] for r in response["rows"]] == [3, 2, 2]
    else:
        assert "PlanDecision" not in calls and response["rows"] == []
    if route != "SQL":
        assert response["sources"][0]["source_file"] == "rules.md"
    assert a.client.get(chat_path).json()["messages"][-1]["response"] == response
    assert b.client.get(chat_path).status_code == 404


@pytest.mark.parametrize("model", ["gemini", "inetcloud-knowledge"])
@pytest.mark.parametrize("route", [RouteLabel.SQL, RouteLabel.RAG, RouteLabel.HYBRID])
def test_guest_three_table_auto_relations_temp_and_pipelines(monkeypatch, model, route):
    settings = get_settings().model_copy(
        update={"sql_join_v1_enabled": True, "ai_default_model": model}
    )
    configure_guest_access(get_setup_engine())
    before = legacy_fingerprints(get_setup_engine())
    store = GuestStore(settings)
    _, context = store.create()
    try:
        for name, content in FILES:
            file = parse_guest_file(name, content, None, settings)
            database = GuestSqlDatabase(settings, [*context.files, file])
            try:
                with database.engine.connect() as connection:
                    previews = detect_relationships(
                        connection, database.file_tables, file.file_id, set()
                    )
            finally:
                database.close()
            records = tuple(
                RelationshipRecord(
                    **p.model_dump(),
                    relationship_id=uuid4().hex,
                    origin="automatic",
                    confirmed=False,
                )
                for p in previews
            )
            store.add_file(context, file, records)
        assert len(context.relationships) == 2
        store.add_file(
            context, parse_guest_file("rules.md", b"# Rule\n\nThreshold 40.", None, settings)
        )
        sql = query("table_1", "table_2", "table_3", order=3, schema="pg_temp")

        class Gateway:
            def generate_structured(self, prompt, schema):
                if schema is TaskProposal:
                    _task_route = route
                    if _task_route in {RouteLabel.RAG, RouteLabel.UNSUPPORTED}:
                        return proposal_for_evidence(
                            "documents" if _task_route == RouteLabel.RAG else "unavailable"
                        )
                    _task_operation = "combine" if _task_route == RouteLabel.HYBRID else "query"
                if schema is TaskProposal:
                    assert "Safe three-table tree" in prompt or '"relationships": [' in prompt
                    return proposal_from_plan(decision_from_sql(sql, prompt), _task_operation)
                if schema is RagAnswerDraft:
                    return RagAnswerDraft(answer="Threshold 40", used_chunk_ids=[1])
                if schema is HybridAnswerDraft:
                    return explanation_draft(prompt, [1])
                raise AssertionError(schema)

            def generate_text(self, prompt):
                assert '"total": null' in prompt
                return "Synthetic SQL"

        monkeypatch.setattr("app.ai.chat.build_generation_gateway", lambda *_: Gateway())
        result = run_guest_chat(
            context.files,
            "Synthetic",
            settings,
            embedder=OfflineEmbedder(),
            relationships=tuple(context.relationships),
        )
        assert result.route == route and result.used_model == model and not result.fallback_used
        if route != RouteLabel.RAG:
            assert result.sql.count("JOIN") == 2
            assert [r["fact_row_count"] for r in result.rows] == [3, 2, 2]
        assert legacy_fingerprints(get_setup_engine()) == before
    finally:
        store.close()


def test_two_fact_join_would_double_totals_but_policy_refuses():
    from app.text_to_sql.join_policy import ApprovedJoin
    from tests.test_three_table_join import PS, validator

    with get_setup_engine().connect() as connection:
        incorrect = connection.scalar(
            text("""
            SELECT SUM(p.amount) FROM (VALUES ('S1',10),('S1',20)) p(student_id,amount)
            JOIN (VALUES ('S1')) s(student_id) ON p.student_id=s.student_id
            JOIN (VALUES ('S1'),('S1')) charges(student_id) ON charges.student_id=s.student_id
        """)
        )
    assert incorrect == 60  # Original fact total is 30, not 60.
    second_fact = ApprovedJoin("second", "courses", "course_id", "students", "student_id", "r")
    sql = (
        "SELECT SUM(p.amount) FROM uploaded_data.payments p "
        "INNER JOIN uploaded_data.students s ON p.student_id=s.student_id "
        "INNER JOIN uploaded_data.courses c ON c.course_id=s.student_id"
    )
    with pytest.raises(SqlUnsupportedError) as error:
        validator((PS, second_fact)).validate(sql)
    assert error.value.code == "join_graph"


@pytest.mark.parametrize(
    "condition,total,count,measured",
    [
        ("c.course_id='C1' AND p.student_id='S2'", "0.00", 1, 1),
        ("c.course_id='C2'", None, 2, 0),
        ("c.course_id='missing'", None, 0, 0),
    ],
)
def test_scalar_zero_all_null_and_empty_three_table_results(
    workspace,
    condition,
    total,
    count,
    measured,
):
    from decimal import Decimal

    from sqlglot import exp, parse_one

    _, dataset, _, context = workspace
    root = parse_one(query(*(t.physical_table_name for t in dataset.tables)), read="postgres")
    root.set("expressions", root.expressions[2:])
    root.set("group", None)
    root.set("order", None)
    root = root.where(condition)
    validator = scoped_validator(context)
    relations = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    validated = validator.validate(root.sql(dialect="postgres"))
    with relations.execution_guard(dataset.dataset_id, context.approved_joins, validated):
        rows = SqlExecutor(get_readonly_engine(), 3000, 100).execute(validated)
    assert len(rows) == 1
    assert rows[0]["total"] == total
    assert rows[0]["fact_row_count"] == count and rows[0]["fact_value_count"] == measured
    assert rows[0]["average"] is None if total is None else Decimal(rows[0]["average"]) == 0
    assert len(list(parse_one(validated.statement).find_all(exp.Join))) == 2


def test_three_table_bigint_projection_is_lossless(workspace):
    from sqlglot import exp, parse_one

    _, dataset, _, context = workspace
    root = parse_one(query(*(t.physical_table_name for t in dataset.tables)), read="postgres")
    root.set("expressions", [exp.column("payment_id", "p"), exp.column("units", "p")])
    root.set("group", None)
    root.set("order", None)
    validated = scoped_validator(context).validate(root.sql(dialect="postgres"))
    with RelationshipRepository(get_setup_engine(), TEST_OWNER).execution_guard(
        dataset.dataset_id,
        context.approved_joins,
        validated,
    ):
        rows = SqlExecutor(get_readonly_engine(), 3000, 100).execute(validated)
    assert next(r for r in rows if r["payment_id"] == "P1")["units"] == "9007199254740993"


@pytest.mark.parametrize("reverse", [False, True])
def test_star_three_table_executes_without_fanout(reverse):
    repo = DatasetRepository(get_setup_engine(), get_readonly_engine(), TEST_OWNER)
    dataset = repo.create_workspace("Three-table star " + uuid4().hex)
    try:
        files = [
            ("students.csv", b"Student id,Name\nS1,An\nS2,Binh\n"),
            ("courses.csv", b"Course id,Title\nC1,SQL\nC2,RAG\n"),
            (
                "payments.csv",
                b"Student id,Course id,Amount\nS1,C1,20.00\nS1,C1,0.00\nS2,C2,0.00\nS2,C2,\n",
            ),
        ]
        for name, content in files:
            dataset = repo.add_table(
                dataset.dataset_id, parse(name, content), auto_relationships=True
            )
        context = build_workspace_context(
            get_settings().model_copy(update={"sql_join_v1_enabled": True}), dataset, repo
        )
        assert len(context.approved_joins) == 2
        s, c, p = ("uploaded_data." + t.physical_table_name for t in dataset.tables)
        bindings = (
            f"FROM {c} c INNER JOIN {p} p ON p.course_id=c.course_id "
            f"INNER JOIN {s} s ON p.student_id=s.student_id"
            if reverse
            else f"FROM {p} p INNER JOIN {s} s ON p.student_id=s.student_id "
            f"INNER JOIN {c} c ON p.course_id=c.course_id"
        )
        sql = (
            "SELECT c.course_id,SUM(p.amount) AS total,COUNT(p.course_id) AS fact_row_count "
            + bindings
            + " GROUP BY c.course_id ORDER BY c.course_id"
        )
        validated = scoped_validator(context).validate(sql)
        with RelationshipRepository(get_setup_engine(), TEST_OWNER).execution_guard(
            dataset.dataset_id,
            context.approved_joins,
            validated,
        ):
            rows = SqlExecutor(get_readonly_engine(), 3000, 100).execute(validated)
        assert rows == [
            {"course_id": "C1", "total": "20.00", "fact_row_count": 2},
            {"course_id": "C2", "total": "0.00", "fact_row_count": 2},
        ]
    finally:
        repo.delete(dataset.dataset_id, delete_conversations=True)


def test_three_table_guard_cannot_ignore_second_id_or_accept_duplicate_ids(workspace):
    from dataclasses import replace

    _, dataset, _, context = workspace
    validated = scoped_validator(context).validate(
        query(*(t.physical_table_name for t in dataset.tables))
    )
    repo = RelationshipRepository(get_setup_engine(), TEST_OWNER)
    for approved, ids in [
        (context.approved_joins[:1], validated.relationship_ids),
        (context.approved_joins, (validated.relationship_ids[0],) * 2),
        (context.approved_joins, (*validated.relationship_ids, "missing")),
    ]:
        with (
            pytest.raises(ResourceConflictError),
            repo.execution_guard(
                dataset.dataset_id,
                approved,
                replace(validated, relationship_ids=ids),
            ),
        ):
            pytest.fail("Incomplete relationship guard yielded")


def test_foreign_workspace_third_table_and_wrong_owner_do_not_reach_executor(workspace):
    from app.core.errors import ResourceNotFoundError, SqlValidationError

    repo, dataset, _, context = workspace
    other = repo.create("Foreign third table " + uuid4().hex, parse(*FILES[0]))
    try:
        names = [t.physical_table_name for t in dataset.tables]
        names[0] = other.table.physical_table_name
        executor, gateway = Mock(), Mock()
        pipeline = ValidationPipeline(
            Mock(generate=Mock(return_value=query(*names))),
            scoped_validator(context),
            executor,
            gateway,
        )
        with pytest.raises(SqlValidationError):
            pipeline.run("Cross-workspace third table")
        executor.execute.assert_not_called()
        gateway.generate_text.assert_not_called()
        validated = scoped_validator(context).validate(
            query(*(t.physical_table_name for t in dataset.tables))
        )
        with (
            pytest.raises(ResourceNotFoundError),
            RelationshipRepository(
                get_setup_engine(),
                uuid4(),
            ).execution_guard(dataset.dataset_id, context.approved_joins, validated),
        ):
            pytest.fail("Wrong owner passed a three-table execution guard")
    finally:
        repo.delete(other.dataset_id, delete_conversations=True)
