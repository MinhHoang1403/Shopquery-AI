"""PDF text is PostgreSQL-safe before any embedding; no live provider requests."""

import pytest
from sqlalchemy import select

from app.database.models import DocumentChunk
from tests.test_auth_integration import accounts  # noqa: F401
from tests.test_document_upload_parser import _pdf_bytes

pytestmark = pytest.mark.integration


def test_pdf_nul_upload_persists_and_duplicate_does_not_reembed(accounts, monkeypatch):  # noqa: F811
    account = accounts.a
    dataset = account.datasets.create_workspace("Synthetic PDF upload")
    calls, closed = [], []

    class OfflineGateway:
        def __init__(self, settings):
            pass

        def embed_document(self, title, content):
            assert "\x00" not in title + content
            calls.append((title, content))
            return [1.0, *([0.0] * 767)]

        def close(self):
            closed.append(True)

    monkeypatch.setattr("app.api.routes.GeminiGateway", OfflineGateway)
    path = f"/api/datasets/{dataset.dataset_id}/documents"
    content = _pdf_bytes("Service\x00handbook: fee 0.00")
    files = {"file": ("handbook.pdf", content, "application/pdf")}
    response = account.client.post(path, files=files)
    assert response.status_code == 201, response.text
    document_id = response.json()["document_id"]
    assert len(calls) == 1 and len(closed) == 1
    assert "Service handbook: fee 0.00" in calls[0][1]
    with accounts.engine.connect() as connection:
        rows = (
            connection.execute(
                select(DocumentChunk.content).where(
                    DocumentChunk.dataset_document_id == document_id
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1 and "Service handbook: fee 0.00" in rows[0]
    assert account.client.get(path).json()[0]["document_id"] == document_id
    assert accounts.b.client.get(path).status_code == 404
    assert account.client.post(path, files=files).status_code == 409
    assert len(calls) == 1
    before = len(closed)
    assert (
        account.client.post(
            path, files={"file": ("unreadable.pdf", _pdf_bytes("\x00\x00"))}
        ).status_code
        == 422
    )
    assert len(calls) == 1 and len(closed) == before
