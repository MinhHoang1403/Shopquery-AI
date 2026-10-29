"""Validate every chunk against storage before any embedding request or DB lookup."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.errors import UploadValidationError
from app.rag.chunking import chunk_document
from app.rag.repository import DocumentRepository
from app.rag.upload_parser import parse_document_file


def test_exact_storage_boundaries_preserve_original_metadata():
    from app.database.models import DocumentChunk

    filename = "a" * 197 + ".md"
    parsed = parse_document_file(filename, ("# " + "H" * 300 + "\n\nBody.").encode())
    chunk = chunk_document(parsed.document)[0]
    assert chunk.source_file == filename and len(chunk.source_file) == 200
    assert chunk.section_title == "H" * 300
    assert DocumentChunk.__table__.c.source_file.type.length == 200
    assert DocumentChunk.__table__.c.section_title.type.length == 300


@pytest.mark.parametrize(
    "filename,body",
    [
        ("a" * 210 + ".md", b"Useful evidence body."),
        ("synthetic.md", ("# " + "A" * 301 + "\n\nEvidence body.").encode()),
        ("synthetic.md", ("# " + "A" * 150 + "\n## " + "B" * 150 + "\n\nBody.").encode()),
    ],
)
def test_chunk_storage_bounds_reject_without_truncating_identity(filename, body):
    parsed = parse_document_file(filename, body)
    with pytest.raises(UploadValidationError):
        chunk_document(parsed.document)


def test_repository_rejects_invalid_chunks_before_embeddings(monkeypatch):
    parsed = parse_document_file("valid.md", b"# Heading\n\nEvidence body.")
    repository = DocumentRepository(Mock(), Mock(), uuid4())
    monkeypatch.setattr(repository, "_require_dataset", lambda _: None)
    # sync is also a public embedding boundary; callers may supply chunk objects.
    chunks = chunk_document(parsed.document)
    chunks[0].source_file = "a" * 201
    embedder = Mock()
    with pytest.raises(UploadValidationError):
        repository.sync(chunks, embedder)
    embedder.embed_document.assert_not_called()
