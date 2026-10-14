"""PostgreSQL persistence and exact cosine retrieval for document chunks."""

from dataclasses import dataclass

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.ai.gemini import EmbeddingGateway
from app.database.models import DocumentChunk
from app.rag.chunking import DocumentChunkData


@dataclass
class RetrievedChunk:
    chunk_id: int
    source_file: str
    section_title: str
    content: str
    cosine_distance: float


class DocumentRepository:
    def __init__(self, setup_engine: Engine, readonly_engine: Engine | None = None) -> None:
        self._setup_engine = setup_engine
        self._readonly_engine = readonly_engine or setup_engine

    def sync(
        self, chunks: list[DocumentChunkData], embedder: EmbeddingGateway
    ) -> dict[str, int]:
        """Embed only new chunks, insert them, and remove stale source revisions."""

        incoming_hashes = {chunk.content_hash for chunk in chunks}
        source_files = {chunk.source_file for chunk in chunks}
        with Session(self._setup_engine) as session:
            existing_hashes = set(
                session.scalars(
                    select(DocumentChunk.content_hash).where(
                        DocumentChunk.source_file.in_(source_files)
                    )
                )
            )
            new_chunks = [chunk for chunk in chunks if chunk.content_hash not in existing_hashes]
            for chunk in new_chunks:
                session.add(
                    DocumentChunk(
                        source_file=chunk.source_file,
                        section_title=chunk.section_title,
                        content=chunk.content,
                        content_hash=chunk.content_hash,
                        embedding=embedder.embed_document(
                            chunk.section_title, chunk.content
                        ),
                    )
                )
            stale_hashes = existing_hashes - incoming_hashes
            if stale_hashes:
                session.execute(
                    delete(DocumentChunk).where(DocumentChunk.content_hash.in_(stale_hashes))
                )
            session.commit()
        return {"total": len(chunks), "embedded": len(new_chunks), "removed": len(stale_hashes)}

    def retrieve(self, query_vector: list[float], top_k: int = 3) -> list[RetrievedChunk]:
        distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")
        statement = select(DocumentChunk, distance).order_by(distance).limit(top_k)
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
