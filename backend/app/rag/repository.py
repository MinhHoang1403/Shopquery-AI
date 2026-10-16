"""PostgreSQL persistence and dataset-scoped vector retrieval."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

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
from app.rag.chunking import DocumentChunkData, chunk_document
from app.rag.upload_parser import ParsedDocument


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    source_file: str
    section_title: str
    content: str
    cosine_distance: float


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
    def __init__(self, setup_engine: Engine, readonly_engine: Engine | None = None) -> None:
        self._setup_engine = setup_engine
        self._readonly_engine = readonly_engine or setup_engine

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
            raise UploadValidationError(
                "Tài liệu không có nội dung bên dưới tiêu đề để tạo chunk."
            )
        embeddings = [
            embedder.embed_document(chunk.section_title, chunk.content) for chunk in chunks
        ]
        try:
            with Session(self._setup_engine) as session:
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
                session.commit()
                document_id = document.document_id
        except IntegrityError as exc:
            raise ResourceConflictError("Tài liệu này đã tồn tại trong bộ dữ liệu.") from exc
        return self.get_document(dataset_id, document_id)

    def delete_document(self, dataset_id: int, document_id: int) -> None:
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
        distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")
        scope = (
            DocumentChunk.dataset_id.is_(None)
            if dataset_id is None
            else DocumentChunk.dataset_id == dataset_id
        )
        statement = select(DocumentChunk, distance).where(scope).order_by(distance).limit(top_k)
        with Session(self._readonly_engine) as session:
            results = session.execute(statement).all()
        return [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                source_file=chunk.source_file,
                section_title=chunk.section_title,
                content=chunk.content,
                cosine_distance=float(score),
            )
            for chunk, score in results
        ]

    def _require_dataset(self, dataset_id: int) -> None:
        with Session(self._setup_engine) as session:
            exists = session.scalar(
                select(Dataset.dataset_id).where(Dataset.dataset_id == dataset_id)
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
