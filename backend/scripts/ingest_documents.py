"""Load, chunk, embed, and synchronize the Markdown policy corpus."""

from app.ai.gemini import GeminiGateway
from app.core.config import get_settings
from app.database.session import get_setup_engine
from app.database.setup import create_schema
from app.rag.chunking import chunk_document
from app.rag.documents import load_markdown_documents
from app.rag.repository import DocumentRepository


def main() -> None:
    settings = get_settings()
    documents = load_markdown_documents(settings.documents_directory)
    if len(documents) != 6:
        raise RuntimeError(f"Expected 6 Markdown documents, found {len(documents)}")
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    engine = get_setup_engine()
    create_schema(engine)
    result = DocumentRepository(engine).sync(chunks, GeminiGateway(settings))
    print(f"Document ingestion completed: {result}")


if __name__ == "__main__":
    main()
