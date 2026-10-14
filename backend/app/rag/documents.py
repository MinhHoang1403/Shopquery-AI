"""UTF-8 Markdown loading with conservative whitespace cleanup."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MarkdownDocument:
    source_file: str
    title: str
    content: str


def load_markdown_documents(directory: Path) -> list[MarkdownDocument]:
    """Load every Markdown file while preserving headings and policy lists."""

    documents: list[MarkdownDocument] = []
    for path in sorted(directory.glob("*.md")):
        raw_content = path.read_text(encoding="utf-8")
        content = _clean_markdown(raw_content)
        title_match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem
        documents.append(MarkdownDocument(path.name, title, content))
    return documents


def _clean_markdown(content: str) -> str:
    lines = [line.rstrip() for line in content.replace("\r\n", "\n").split("\n")]
    cleaned: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        cleaned.append(line)
        previous_blank = is_blank
    return "\n".join(cleaned).strip()
