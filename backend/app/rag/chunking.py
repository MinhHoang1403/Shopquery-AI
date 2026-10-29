"""Markdown heading-aware chunking with paragraph-boundary fallback."""

import hashlib
import re
from dataclasses import dataclass

from app.rag.documents import MarkdownDocument
from app.rag.storage_contract import validate_storage_metadata

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class DocumentChunkData:
    source_file: str
    section_title: str
    content: str
    content_hash: str


def chunk_document(
    document: MarkdownDocument,
    target_words: int = 300,
    overlap_words: int = 30,
) -> list[DocumentChunkData]:
    """Keep short sections intact and split long ones at paragraph boundaries."""

    sections = _extract_sections(document)
    chunks: list[DocumentChunkData] = []
    for section_title, paragraphs in sections:
        content = "\n\n".join(paragraphs).strip()
        if not content:
            continue
        validate_storage_metadata(document.source_file, section_title)
        for part in _split_long_section(content, target_words, overlap_words):
            digest_source = f"{document.source_file}\n{section_title}\n{part}"
            chunks.append(
                DocumentChunkData(
                    source_file=document.source_file,
                    section_title=section_title,
                    content=part,
                    content_hash=hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
                )
            )
    return chunks


def _extract_sections(document: MarkdownDocument) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    heading_path: list[tuple[int, str]] = []
    current_title = document.title
    current_lines: list[str] = []

    def flush() -> None:
        paragraphs = _to_paragraphs(current_lines)
        if paragraphs:
            sections.append((current_title, paragraphs))

    for line in document.content.splitlines():
        heading = HEADING_PATTERN.match(line)
        if heading:
            flush()
            current_lines = []
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_path = [item for item in heading_path if item[0] < level]
            heading_path.append((level, title))
            current_title = " > ".join(item[1] for item in heading_path)
        else:
            current_lines.append(line)
    flush()
    return sections


def _to_paragraphs(lines: list[str]) -> list[str]:
    return [part.strip() for part in "\n".join(lines).split("\n\n") if part.strip()]


def _split_long_section(
    content: str, target_words: int, overlap_words: int
) -> list[str]:
    words = content.split()
    if len(words) <= target_words:
        return [content]
    paragraphs = content.split("\n\n")
    parts: list[str] = []
    current: list[str] = []
    current_size = 0
    for paragraph in paragraphs:
        paragraph_words = paragraph.split()
        if current and current_size + len(paragraph_words) > target_words:
            part = "\n\n".join(current)
            parts.append(part)
            overlap = " ".join(part.split()[-overlap_words:]) if overlap_words else ""
            current = [overlap, paragraph] if overlap else [paragraph]
            current_size = len(current[0].split()) + len(paragraph_words)
        elif len(paragraph_words) > target_words:
            if current:
                parts.append("\n\n".join(current))
                current = []
                current_size = 0
            step = max(1, target_words - overlap_words)
            for start in range(0, len(paragraph_words), step):
                window = paragraph_words[start : start + target_words]
                parts.append(" ".join(window))
                if start + target_words >= len(paragraph_words):
                    break
        else:
            current.append(paragraph)
            current_size += len(paragraph_words)
    if current:
        parts.append("\n\n".join(current))
    return parts
