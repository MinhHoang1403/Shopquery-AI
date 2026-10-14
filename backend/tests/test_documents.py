"""Markdown loading and heading-aware chunking tests."""

from app.core.config import get_settings
from app.rag.chunking import chunk_document
from app.rag.documents import load_markdown_documents


def test_loads_six_documents_with_metadata() -> None:
    documents = load_markdown_documents(get_settings().documents_directory)
    assert len(documents) == 6
    assert {document.source_file for document in documents} == {
        "shipping_policy.md",
        "return_policy.md",
        "warranty_policy.md",
        "product_guide.md",
        "shopping_guide.md",
        "faq.md",
    }


def test_chunking_preserves_policy_conditions_and_unique_hashes() -> None:
    documents = load_markdown_documents(get_settings().documents_directory)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    content = "\n".join(chunk.content for chunk in chunks)

    assert len(chunks) == 25
    assert len({chunk.content_hash for chunk in chunks}) == len(chunks)
    assert "PHONE và LAPTOP được miễn phí vận chuyển" in content
    assert "trong vòng 14 ngày" in content
    assert "AUDIO và ACCESSORY được bảo hành 6 tháng" in content
    assert all(chunk.section_title and chunk.source_file for chunk in chunks)
