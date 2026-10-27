"""PostgreSQL persistence and dataset-scoped vector retrieval."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.gemini import EmbeddingGateway
from app.core.errors import (
    ResourceConflictError,
    ResourceNotFoundError,
    UploadValidationError,
)
from app.database.models import Dataset, DatasetDocument, DocumentChunk
from app.database.quotas import enforce_storage_budget, lock_owner_budget
from app.rag.chunking import DocumentChunkData, chunk_document
from app.rag.upload_parser import ParsedDocument


@dataclass(frozen=True)
class DocumentScope:
    document_id: int | str
    content_hash: str
    chunk_ids: tuple[int, ...]
    dataset_id: int
    owner_user_id: UUID | None
    text_hashes: tuple[tuple[int, str], ...] = ()
    document_parts: tuple[tuple[int, str, str], ...] = ()


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    source_file: str
    section_title: str
    content: str
    cosine_distance: float
    document_scope: DocumentScope | None = None


@dataclass(frozen=True)
class DatasetDocumentInfo:
    document_id: int
    dataset_id: int
    original_filename: str
    file_type: str
    title: str
    content_hash: str
    chunk_count: int
    created_at: datetime


class DocumentRepository:
    def __init__(
        self,
        setup_engine: Engine,
        readonly_engine: Engine | None = None,
        owner_user_id: UUID | None = None,
    ) -> None:
        self._setup_engine = setup_engine
        self._readonly_engine = readonly_engine or setup_engine
        self._owner_user_id = owner_user_id

    def sync(self, chunks: list[DocumentChunkData], embedder: EmbeddingGateway) -> dict[str, int]:
        """Synchronize only the legacy/default corpus."""

        incoming_hashes = {chunk.content_hash for chunk in chunks}
        source_files = {chunk.source_file for chunk in chunks}
        with Session(self._setup_engine) as session:
            existing_hashes = set(
                session.scalars(
                    select(DocumentChunk.content_hash).where(
                        DocumentChunk.dataset_id.is_(None),
                        DocumentChunk.source_file.in_(source_files),
                    )
                )
            )
            new_chunks = [chunk for chunk in chunks if chunk.content_hash not in existing_hashes]
            embeddings = [
                embedder.embed_document(chunk.section_title, chunk.content) for chunk in new_chunks
            ]
            for chunk, embedding in zip(new_chunks, embeddings, strict=True):
                session.add(
                    DocumentChunk(
                        source_file=chunk.source_file,
                        section_title=chunk.section_title,
                        content=chunk.content,
                        content_hash=chunk.content_hash,
                        embedding=embedding,
                    )
                )
            stale_hashes = existing_hashes - incoming_hashes
            if stale_hashes:
                session.execute(
                    delete(DocumentChunk).where(
                        DocumentChunk.dataset_id.is_(None),
                        DocumentChunk.content_hash.in_(stale_hashes),
                    )
                )
            session.commit()
        return {
            "total": len(chunks),
            "embedded": len(new_chunks),
            "removed": len(stale_hashes),
        }

    def list_documents(self, dataset_id: int) -> list[DatasetDocumentInfo]:
        self._require_dataset(dataset_id)
        with Session(self._setup_engine) as session:
            documents = session.scalars(
                select(DatasetDocument)
                .where(DatasetDocument.dataset_id == dataset_id)
                .order_by(DatasetDocument.created_at.desc(), DatasetDocument.document_id.desc())
            ).all()
        return [self._to_info(item) for item in documents]

    def get_document(self, dataset_id: int, document_id: int) -> DatasetDocumentInfo:
        self._require_dataset(dataset_id)
        with Session(self._setup_engine) as session:
            item = session.scalar(
                select(DatasetDocument).where(
                    DatasetDocument.dataset_id == dataset_id,
                    DatasetDocument.document_id == document_id,
                )
            )
        if item is None:
            raise ResourceNotFoundError("Không tìm thấy tài liệu trong bộ dữ liệu.")
        return self._to_info(item)

    def add_document(
        self,
        dataset_id: int,
        parsed: ParsedDocument,
        embedder: EmbeddingGateway,
    ) -> DatasetDocumentInfo:
        self._require_dataset(dataset_id)
        with Session(self._setup_engine) as session:
            duplicate = session.scalar(
                select(DatasetDocument.document_id).where(
                    DatasetDocument.dataset_id == dataset_id,
                    DatasetDocument.content_hash == parsed.content_hash,
                )
            )
        if duplicate is not None:
            raise ResourceConflictError("Tài liệu này đã tồn tại trong bộ dữ liệu.")

        chunks = chunk_document(parsed.document)
        if not chunks:
            raise UploadValidationError("Tài liệu không có nội dung bên dưới tiêu đề để tạo chunk.")
        embeddings = [
            embedder.embed_document(chunk.section_title, chunk.content) for chunk in chunks
        ]
        try:
            with Session(self._setup_engine) as session:
                lock_owner_budget(session.connection(), self._owner_user_id)
                parent = session.scalar(
                    select(Dataset.dataset_id)
                    .where(
                        Dataset.dataset_id == dataset_id,
                        Dataset.owner_user_id == self._owner_user_id,
                    )
                    .with_for_update()
                )
                if parent is None:
                    raise ResourceNotFoundError("Không tìm thấy bộ dữ liệu.")
                document = DatasetDocument(
                    dataset_id=dataset_id,
                    original_filename=parsed.document.source_file,
                    file_type=parsed.file_type,
                    title=parsed.document.title,
                    content_hash=parsed.content_hash,
                    chunk_count=len(chunks),
                )
                session.add(document)
                session.flush()
                for chunk, embedding in zip(chunks, embeddings, strict=True):
                    namespaced_hash = hashlib.sha256(
                        f"dataset:{dataset_id}:{chunk.content_hash}".encode()
                    ).hexdigest()
                    session.add(
                        DocumentChunk(
                            dataset_id=dataset_id,
                            dataset_document_id=document.document_id,
                            source_file=chunk.source_file,
                            section_title=chunk.section_title,
                            content=chunk.content,
                            content_hash=namespaced_hash,
                            embedding=embedding,
                        )
                    )
                session.flush()
                enforce_storage_budget(session.connection(), self._owner_user_id)
                session.commit()
                document_id = document.document_id
        except IntegrityError as exc:
            raise ResourceConflictError("Tài liệu này đã tồn tại trong bộ dữ liệu.") from exc
        return self.get_document(dataset_id, document_id)

    def delete_document(self, dataset_id: int, document_id: int) -> None:
        self._require_dataset(dataset_id)
        with Session(self._setup_engine) as session:
            result = session.execute(
                delete(DatasetDocument).where(
                    DatasetDocument.dataset_id == dataset_id,
                    DatasetDocument.document_id == document_id,
                )
            )
            if result.rowcount != 1:
                session.rollback()
                raise ResourceNotFoundError("Không tìm thấy tài liệu trong bộ dữ liệu.")
            session.commit()

    def retrieve(
        self,
        query_vector: list[float],
        top_k: int = 3,
        *,
        dataset_id: int | None = None,
    ) -> list[RetrievedChunk]:
        if dataset_id is not None:
            self._require_dataset(dataset_id)
        distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")
        scope = (
            DocumentChunk.dataset_id.is_(None)
            if dataset_id is None
            else DocumentChunk.dataset_id == dataset_id
        )
        if dataset_id is not None:
            scope = (
                scope
                & select(Dataset.dataset_id)
                .where(
                    Dataset.dataset_id == dataset_id, Dataset.owner_user_id == self._owner_user_id
                )
                .exists()
            )
        statement = select(DocumentChunk, distance).where(scope).order_by(distance).limit(top_k)
        with Session(self._readonly_engine) as session:
            results = session.execute(statement).all()
            document_ids = {c.dataset_document_id for c, _ in results if c.dataset_document_id}
            documents = (
                session.scalars(
                    select(DatasetDocument).where(
                        DatasetDocument.document_id.in_(document_ids),
                        DatasetDocument.dataset_id == dataset_id,
                    )
                ).all()
                if dataset_id is not None
                else []
            )
            registered = session.execute(
                select(
                    DocumentChunk.dataset_document_id,
                    DocumentChunk.chunk_id,
                    DocumentChunk.section_title,
                    DocumentChunk.content,
                ).where(DocumentChunk.dataset_document_id.in_(document_ids), scope)
            ).all()
            scopes = {}
            for document in documents:
                parts = tuple(
                    sorted(
                        (i, title, content)
                        for d, i, title, content in registered
                        if d == document.document_id
                    )
                )
                ids = tuple(i for i, _, _ in parts)
                if len(ids) == document.chunk_count:
                    scopes[document.document_id] = DocumentScope(
                        document.document_id,
                        document.content_hash,
                        ids,
                        dataset_id,
                        self._owner_user_id,
                        tuple(
                            (i, hashlib.sha256(content.encode()).hexdigest())
                            for i, _, content in parts
                        ),
                        parts
                        if len(parts) <= 20
                        and sum(len(content) for _, _, content in parts) <= 60000
                        else (),
                    )
        return [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                source_file=chunk.source_file,
                section_title=chunk.section_title,
                content=chunk.content,
                cosine_distance=float(score),
                document_scope=scopes.get(chunk.dataset_document_id),
            )
            for chunk, score in results
        ]

    def _require_dataset(self, dataset_id: int) -> None:
        if self._owner_user_id is None:
            raise ResourceNotFoundError("Không tìm thấy bộ dữ liệu.")
        with Session(self._setup_engine) as session:
            exists = session.scalar(
                select(Dataset.dataset_id).where(
                    Dataset.dataset_id == dataset_id, Dataset.owner_user_id == self._owner_user_id
                )
            )
        if exists is None:
            raise ResourceNotFoundError("Không tìm thấy bộ dữ liệu.")

    @staticmethod
    def _to_info(item: DatasetDocument) -> DatasetDocumentInfo:
        return DatasetDocumentInfo(
            document_id=item.document_id,
            dataset_id=item.dataset_id,
            original_filename=item.original_filename,
            file_type=item.file_type,
            title=item.title,
            content_hash=item.content_hash,
            chunk_count=item.chunk_count,
            created_at=item.created_at,
        )
