"""Real PostgreSQL deletion, scope, cascade and transaction rollback checks."""

from contextlib import suppress
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.conversations.repository import ConversationRepository
from app.core.errors import ResourceConflictError, ResourceNotFoundError
from app.database.models import ChatMessage, Dataset, DatasetDocument, DatasetTable, DocumentChunk
from app.database.session import get_readonly_engine, get_setup_engine
from app.database.setup import create_schema
from app.datasets.parser import parse_tabular_file
from app.datasets.repository import DatasetRepository
from app.rag.documents import MarkdownDocument
from app.rag.repository import DocumentRepository
from app.rag.upload_parser import ParsedDocument

pytestmark = pytest.mark.integration


class Embedder:
    def embed_document(self, title: str, content: str) -> list[float]:
        return [1.0, *([0.0] * 767)]


@pytest.fixture
def sources():
    engine = get_setup_engine()
    create_schema(engine)
    datasets = DatasetRepository(engine, get_readonly_engine())
    documents = DocumentRepository(engine)
    chats = ConversationRepository(engine)
    created: list[int] = []

    def create():
        dataset = datasets.create(
            f"Delete fixture {uuid4().hex}",
            parse_tabular_file(
                "first.csv", b"Value\n1\n", max_bytes=1024, max_rows=10, max_columns=10
            ),
        )
        created.append(dataset.dataset_id)
        dataset = datasets.add_table(
            dataset.dataset_id,
            parse_tabular_file(
                "second.csv", b"Count\n2\n3\n", max_bytes=1024, max_rows=10, max_columns=10
            ),
        )
        document = documents.add_document(
            dataset.dataset_id,
            ParsedDocument(
                MarkdownDocument("policy.md", "Policy", "# Policy\n\nFixture."),
                "md",
                uuid4().hex * 2,
            ),
            Embedder(),
        )
        conversation = chats.create(dataset.dataset_id)
        message = chats.add_user_message(conversation.conversation_id, "Saved question")
        return dataset, document, conversation, message

    yield engine, datasets, documents, chats, create
    for dataset_id in created:
        with suppress(ResourceNotFoundError):
            datasets.delete(dataset_id, delete_conversations=True)


def exists(engine, name: str) -> bool:
    with engine.connect() as connection:
        return (
            connection.scalar(text("SELECT to_regclass(:name)"), {"name": f"uploaded_data.{name}"})
            is not None
        )


def test_delete_one_table_keeps_other_sources_and_history(sources) -> None:
    engine, datasets, documents, chats, create = sources
    dataset, document, conversation, _ = create()
    first, second = dataset.tables
    datasets.delete_table(dataset.dataset_id, first.dataset_table_id)
    remaining = datasets.get(dataset.dataset_id)
    assert not exists(engine, first.physical_table_name)
    assert exists(engine, second.physical_table_name)
    assert remaining.table_count == 1
    assert remaining.original_filename == "second.csv"
    assert remaining.row_count == 2
    assert datasets.preview_rows(dataset.dataset_id) == [{"Count": 2}, {"Count": 3}]
    assert documents.get_document(dataset.dataset_id, document.document_id)
    assert len(chats.get(conversation.conversation_id).messages) == 1
    with pytest.raises(ResourceNotFoundError):
        datasets.delete_table(dataset.dataset_id, first.dataset_table_id)
    datasets.delete_table(dataset.dataset_id, second.dataset_table_id)
    empty = datasets.get(dataset.dataset_id)
    assert empty.table is None
    assert empty.original_filename is None
    assert empty.row_count is None
    assert empty.document_count == 1


def test_delete_requires_history_consent_and_cascades_only_selected_workspace(sources) -> None:
    engine, datasets, documents, chats, create = sources
    dataset, document, conversation, message = create()
    other, other_document, other_chat, _ = create()
    with engine.connect() as connection:
        default_chunks = connection.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.dataset_id.is_(None))
        )
    with pytest.raises(ResourceConflictError):
        datasets.delete(dataset.dataset_id)
    assert all(exists(engine, item.physical_table_name) for item in dataset.tables)
    assert chats.get(conversation.conversation_id)
    with pytest.raises(ResourceNotFoundError):
        datasets.delete_table(other.dataset_id, dataset.tables[0].dataset_table_id)
    documents.delete_document(dataset.dataset_id, document.document_id)
    assert documents.list_documents(dataset.dataset_id) == []
    assert documents.get_document(other.dataset_id, other_document.document_id)
    datasets.delete(dataset.dataset_id, delete_conversations=True)
    assert all(not exists(engine, item.physical_table_name) for item in dataset.tables)
    with pytest.raises(ResourceNotFoundError):
        datasets.get(dataset.dataset_id)
    with pytest.raises(ResourceNotFoundError):
        chats.get(conversation.conversation_id)
    with engine.connect() as connection:
        assert (
            connection.scalar(
                select(ChatMessage.message_id).where(ChatMessage.message_id == message.message_id)
            )
            is None
        )
        for model in (DatasetTable, DatasetDocument, DocumentChunk):
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.dataset_id == dataset.dataset_id)
                )
                == 0
            )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.dataset_id.is_(None))
            )
            == default_chunks
        )
    assert datasets.get(other.dataset_id).table_count == 2
    assert documents.get_document(other.dataset_id, other_document.document_id)
    assert chats.get(other_chat.conversation_id)


def test_whole_dataset_delete_removes_document_embeddings(sources) -> None:
    engine, datasets, _, _, create = sources
    dataset, _, _, _ = create()
    datasets.delete(dataset.dataset_id, delete_conversations=True)
    with engine.connect() as connection:
        for model in (Dataset, DatasetTable, DatasetDocument, DocumentChunk):
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.dataset_id == dataset.dataset_id)
                )
                == 0
            )


def test_delete_failure_rolls_back_physical_tables_metadata_and_history(
    sources, monkeypatch
) -> None:
    engine, datasets, documents, chats, create = sources
    dataset, document, conversation, _ = create()
    original_table = datasets._table

    def fail_second(name, columns):
        if name == dataset.tables[1].physical_table_name:
            raise RuntimeError("simulated drop failure")
        return original_table(name, columns)

    with monkeypatch.context() as patch:
        patch.setattr(datasets, "_table", fail_second)
        with pytest.raises(RuntimeError, match="simulated drop failure"):
            datasets.delete(dataset.dataset_id, delete_conversations=True)
    assert all(exists(engine, item.physical_table_name) for item in dataset.tables)
    assert datasets.get(dataset.dataset_id).table_count == 2
    assert documents.get_document(dataset.dataset_id, document.document_id)
    assert chats.get(conversation.conversation_id).messages


def test_empty_workspace_can_be_deleted_without_history_consent(sources) -> None:
    _, datasets, _, _, _ = sources
    workspace = datasets.create_workspace(f"Empty deletion {uuid4().hex}")
    datasets.delete(workspace.dataset_id)
    with pytest.raises(ResourceNotFoundError):
        datasets.delete(workspace.dataset_id)
