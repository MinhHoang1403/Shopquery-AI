"""Safety and format coverage for dataset document uploads."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.core.errors import UploadValidationError
from app.rag.upload_parser import parse_document_file


def _docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_heading("Chính sách", level=1)
    document.add_paragraph(text)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _pdf_bytes(text: str | None = None, *, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if text is not None:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_ref = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_ref}
                )
            }
        )
        stream = StreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize("extension", ["txt", "md"])
def test_parses_utf8_text_and_sanitizes_filename(extension: str) -> None:
    parsed = parse_document_file(
        f"../../chính-sách.{extension}",
        "# Đổi trả\n\nKhách hàng được đổi trong 14 ngày.".encode(),
    )

    assert parsed.document.source_file == f"chính-sách.{extension}"
    assert parsed.document.title == "Đổi trả"
    assert "14 ngày" in parsed.document.content


def test_parses_docx_without_extracting_archive_to_disk() -> None:
    parsed = parse_document_file(
        "quy-dinh.docx", _docx_bytes("Miễn phí vận chuyển từ 500.000đ.")
    )

    assert parsed.file_type == "docx"
    assert parsed.document.title == "Chính sách"
    assert "500.000đ" in parsed.document.content


def test_parses_text_pdf_and_rejects_scanned_or_encrypted_pdf() -> None:
    parsed = parse_document_file("policy.pdf", _pdf_bytes("Return within 14 days"))

    assert "Return within 14 days" in parsed.document.content
    with pytest.raises(UploadValidationError, match="OCR"):
        parse_document_file("scan.pdf", _pdf_bytes())
    with pytest.raises(UploadValidationError, match="mã hóa"):
        parse_document_file("secret.pdf", _pdf_bytes(encrypted=True))


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("empty.txt", b"", "trống"),
        ("bad.txt", b"\xff\xfe", "UTF-8"),
        ("bad.pdf", b"not a pdf", "chữ ký PDF"),
        ("bad.docx", b"PK broken", "DOCX"),
        ("heading.md", "# Chỉ có tiêu đề".encode(), "chỉ có tiêu đề"),
        ("legacy.doc", b"legacy", "PDF, DOCX, TXT hoặc MD"),
    ],
)
def test_rejects_empty_corrupt_and_unsupported_documents(
    filename: str, content: bytes, message: str
) -> None:
    with pytest.raises(UploadValidationError, match=message):
        parse_document_file(filename, content)


def test_rejects_oversized_and_zip_bomb_metadata() -> None:
    with pytest.raises(UploadValidationError, match="giới hạn"):
        parse_document_file("large.txt", b"a" * 11, max_bytes=10)

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("word/document.xml", b"x" * 100_000)
    with pytest.raises(UploadValidationError, match="tỷ lệ nén"):
        parse_document_file("bomb.docx", output.getvalue())
