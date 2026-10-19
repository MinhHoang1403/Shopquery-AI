"""Guest relationship checks use only session files and restricted TEMP tables."""

import threading

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.database.guest_access import configure_guest_access
from app.database.integrity import legacy_fingerprints
from app.database.session import get_setup_engine
from app.datasets.relationships import RelationshipInput, RelationshipRecord, verify_relationship
from app.guest.pipeline import GuestSqlDatabase, run_guest_chat
from app.guest.store import GuestStore
from app.guest.worker import parse_guest_file, run_isolated
from app.rag.pipeline import RagAnswerDraft
from app.routing.hybrid import HybridAnswerDraft
from app.routing.router import RouteDecision, RouteLabel
from app.text_to_sql.generator import SqlDraft
from tests.test_guest_integration import OfflineEmbedder

pytestmark = pytest.mark.integration


def test_guest_relationship_worker_ram_scope_and_expiry() -> None:
    settings = get_settings().model_copy(update={"sql_join_v1_enabled": True})
    configure_guest_access(get_setup_engine())
    before = legacy_fingerprints(get_setup_engine())
    files = [
        parse_guest_file("students.csv", b"Id,Name\n101,An\n102,Binh\n", None, settings),
        parse_guest_file(
            "payments.csv", b"Key,Amount\n101,20.0\n101,30.0\n102,0.0\n", None, settings
        ),
    ]
    request = RelationshipInput(
        source_table_id=files[1].file_id,
        source_column="key",
        target_table_id=files[0].file_id,
        target_column="id",
    )
    preview = run_isolated("relationship", (files, request), settings, threading.Event())
    assert preview.valid and preview.cardinality == "many-to-one"
    remapped = run_isolated(
        "relationship", (list(reversed(files)), request), settings, threading.Event()
    )
    assert preview.revision == remapped.revision
    with pytest.raises(HTTPException) as failure:
        run_isolated("relationship", (files[:1], request), settings, threading.Event())
    assert failure.value.status_code == 404
    now = [0.0]
    store = GuestStore(settings, clock=lambda: now[0])
    _, own = store.create()
    _, other = store.create()
    for file in files:
        store.add_file(own, file)
    record = RelationshipRecord(**preview.model_dump(), relationship_id="guest-relation")
    store.confirm_relationship(own, record)
    assert other.relationships == []
    with pytest.raises(HTTPException):
        store.confirm_relationship(other, record)
    now[0] = settings.guest_session_seconds + 1
    store.cleanup()
    assert own.relationships == [] and own.files == [] and own.cancelled.is_set()
    assert legacy_fingerprints(get_setup_engine()) == before


@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize("route", [RouteLabel.SQL, RouteLabel.RAG, RouteLabel.HYBRID])
def test_guest_join_remapping_chat_both_selections_without_persistence(monkeypatch, model, route):
    settings = get_settings().model_copy(
        update={"sql_join_v1_enabled": True, "ai_default_model": model}
    )
    configure_guest_access(get_setup_engine())
    before = legacy_fingerprints(get_setup_engine())
    files = [
        parse_guest_file("students.csv", b"Id,Name\n101,An\n102,Binh\n", None, settings),
        parse_guest_file("payments.csv", b"Key,Amount\n101,20\n101,30\n102,0\n", None, settings),
        parse_guest_file("rules.md", b"# Rules\n\nSynthetic threshold 40.", None, settings),
    ]
    request = RelationshipInput(
        source_table_id=files[1].file_id,
        source_column="key",
        target_table_id=files[0].file_id,
        target_column="id",
    )
    db = GuestSqlDatabase(settings, files)
    try:
        with db.engine.connect() as connection:
            preview = verify_relationship(connection, request, db.file_tables)
    finally:
        db.close()
    record = RelationshipRecord(**preview.model_dump(), relationship_id="ram-only")
    calls = []

    class Gateway:
        def generate_structured(self, prompt, schema):
            calls.append(schema.__name__)
            if schema is RouteDecision:
                return RouteDecision(route=route, reason="Offline remapped JOIN")
            if schema is SqlDraft:
                # Input list is reversed below: payments becomes table_1, students table_2.
                assert "pg_temp.table_1.key = pg_temp.table_2.id" in prompt
                return SqlDraft(
                    sql="SELECT SUM(f.amount) AS total FROM pg_temp.table_1 f "
                    "INNER JOIN pg_temp.table_2 d ON f.key=d.id"
                )
            if schema is RagAnswerDraft:
                return RagAnswerDraft(answer="Threshold 40", used_chunk_ids=[1])
            if schema is HybridAnswerDraft:
                return HybridAnswerDraft(answer="50 exceeds 40", used_chunk_ids=[1])
            raise AssertionError(schema)

        def generate_text(self, prompt):
            calls.append("answer")
            assert '"total": "50"' in prompt
            return "50"

    selected = []

    def build(config, model_id):
        selected.append(model_id)
        return Gateway()

    monkeypatch.setattr("app.ai.chat.build_generation_gateway", build)
    result = run_guest_chat(
        [files[1], files[0], files[2]],
        "Synthetic",
        settings,
        embedder=OfflineEmbedder(),
        relationships=(record,),
    )
    assert result.route == route and result.used_model == model and selected == [model]
    assert len(calls) == {RouteLabel.SQL: 3, RouteLabel.RAG: 2, RouteLabel.HYBRID: 4}[route]
    if route != RouteLabel.RAG:
        assert result.rows == [{"total": "50"}]
    if route != RouteLabel.SQL:
        assert result.sources[0].source_file == "rules.md"
    assert legacy_fingerprints(get_setup_engine()) == before
