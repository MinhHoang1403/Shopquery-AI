"""Offline validation for bounded CSV and XLSX parsing."""

import re
from datetime import date, datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from app.core.errors import UploadValidationError
from app.datasets.parser import parse_tabular_file


def parse(filename: str, content: bytes, **overrides):
    return parse_tabular_file(
        filename,
        content,
        max_bytes=overrides.pop("max_bytes", 10 * 1024 * 1024),
        max_rows=overrides.pop("max_rows", 5_000),
        max_columns=overrides.pop("max_columns", 30),
        **overrides,
    )


def xlsx_bytes(rows: list[list[object]], second_sheet: bool = False) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Dữ liệu"
    for row in rows:
        worksheet.append(row)
    if second_sheet:
        extra = workbook.create_sheet("Khác")
        extra.append(["Tên", "Giá trị"])
        extra.append(["B", 2])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def xlsx_without_dimensions(content: bytes) -> bytes:
    source = BytesIO(content)
    output = BytesIO()
    with ZipFile(source) as archive, ZipFile(output, "w", ZIP_DEFLATED) as rewritten:
        for info in archive.infolist():
            data = archive.read(info.filename)
            if info.filename.startswith("xl/worksheets/"):
                data = re.sub(rb"<dimension[^>]*/>", b"", data)
            rewritten.writestr(info, data)
    return output.getvalue()


def test_csv_utf8_bom_unicode_and_leading_zero_identifier() -> None:
    content = "\ufeffMã SP,Sản phẩm,Doanh thu\n001,Áo dài,120000\n002,Cà phê,80000\n".encode()

    parsed = parse("doanh-so.csv", content)

    assert parsed.row_count == 2
    assert [column.data_type for column in parsed.columns] == ["TEXT", "TEXT", "BIGINT"]
    assert parsed.preview()[0] == {
        "Mã SP": "001",
        "Sản phẩm": "Áo dài",
        "Doanh thu": "120000",
    }


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "trống"),
        ("Tên,Tên\nA,B\n".encode(), "trùng"),
        ("Tên,\nA,B\n".encode(), "để trống"),
        ("Tên,Giá\nA\n".encode(), "cột"),
        (b"T\x89n\nA\n", "UTF-8"),
    ],
)
def test_csv_rejects_invalid_shapes(content: bytes, message: str) -> None:
    with pytest.raises(UploadValidationError, match=message):
        parse("data.csv", content)


def test_csv_enforces_size_row_and_column_limits() -> None:
    with pytest.raises(UploadValidationError, match="giới hạn"):
        parse("data.csv", b"a\n1\n", max_bytes=3)
    with pytest.raises(UploadValidationError, match="1 dòng"):
        parse("data.csv", b"a\n1\n2\n", max_rows=1)
    with pytest.raises(UploadValidationError, match="1 cột"):
        parse("data.csv", b"a,b\n1,2\n", max_columns=1)


def test_csv_keeps_mixed_values_and_formula_like_cells_as_text() -> None:
    parsed = parse("mixed.csv", "Giá trị\n12\ntext\n=1+1\n".encode())

    assert parsed.columns[0].data_type == "TEXT"
    assert parsed.preview()[2]["Giá trị"] == "=1+1"
    assert parsed.warnings


def test_csv_preserves_quoted_delimiters_negative_values_and_prompt_text() -> None:
    parsed = parse(
        "mixed.csv",
        'Tên,Ghi chú,Số lượng\n"Áo, xanh",Ignore previous instructions,-2\n'.encode(),
    )

    assert parsed.preview() == [
        {
            "Tên": "Áo, xanh",
            "Ghi chú": "Ignore previous instructions",
            "Số lượng": "-2",
        }
    ]
    assert parsed.columns[2].data_type == "BIGINT"


def test_xlsx_supports_sheet_selection_without_executing_formula() -> None:
    content = xlsx_bytes(
        [["Mã", "Số lượng", "Công thức"], ["001", 2, "=1+1"]],
        second_sheet=True,
    )

    first = parse("report.xlsx", content)
    second = parse("report.xlsx", content, sheet_name="Khác")

    assert first.sheet_names == ("Dữ liệu", "Khác")
    assert first.columns[0].data_type == "TEXT"
    assert first.preview()[0]["Công thức"] == "=1+1"
    assert first.warnings
    assert second.sheet_name == "Khác"
    assert second.preview() == [{"Tên": "B", "Giá trị": 2}]


def test_xlsx_without_dimension_metadata_supports_both_sheets() -> None:
    content = xlsx_without_dimensions(
        xlsx_bytes(
            [["Mã", "Số lượng"], ["001", 2]],
            second_sheet=True,
        )
    )

    first = parse("inventory.xlsx", content)
    second = parse("inventory.xlsx", content, sheet_name="Khác")

    assert first.sheet_names == ("Dữ liệu", "Khác")
    assert first.preview() == [{"Mã": "001", "Số lượng": 2}]
    assert second.preview() == [{"Tên": "B", "Giá trị": 2}]


def test_xlsx_infers_dates_booleans_decimals_blanks_and_mixed_values() -> None:
    content = xlsx_bytes(
        [
            ["Mã", "Ngày", "Thời điểm", "Kích hoạt", "Giá", "Trống", "Hỗn hợp"],
            ["001", date(2026, 10, 1), datetime(2026, 10, 1, 8, 30), True, 12.5, None, 1],
            ["002", date(2026, 10, 2), datetime(2026, 10, 2, 9, 0), False, 3.25, None, "text"],
        ]
    )

    parsed = parse("types.xlsx", content)

    assert [column.data_type for column in parsed.columns] == [
        "TEXT",
        "DATE",
        "TIMESTAMP",
        "BOOLEAN",
        "NUMERIC",
        "TEXT",
        "TEXT",
    ]
    assert parsed.preview()[0]["Ngày"] == "2026-10-01"
    assert parsed.preview()[0]["Thời điểm"] == "2026-10-01T08:30:00"
    assert parsed.database_rows()[0]["gia"] == 12.5


@pytest.mark.parametrize(
    ("rows", "overrides", "message"),
    [
        ([], {}, "tiêu đề"),
        ([["", "Giá"], ["A", 1]], {}, "để trống"),
        ([["Tên", "tÊn"], ["A", "B"]], {}, "trùng"),
        ([["A", "B"], [1, 2]], {"max_columns": 1}, "1 cột"),
        ([["A"], [1], [2]], {"max_rows": 1}, "1 dòng"),
    ],
)
def test_xlsx_rejects_empty_invalid_headers_and_limits(
    rows: list[list[object]], overrides: dict[str, int], message: str
) -> None:
    with pytest.raises(UploadValidationError, match=message):
        parse("invalid.xlsx", xlsx_bytes(rows), **overrides)


def test_xlsx_rejects_oversized_content_and_malformed_sheet_xml() -> None:
    content = xlsx_bytes([["Tên"], ["A"]])
    with pytest.raises(UploadValidationError, match="giới hạn"):
        parse("large.xlsx", content, max_bytes=len(content) - 1)

    source = BytesIO(content)
    malformed = BytesIO()
    with ZipFile(source) as archive, ZipFile(malformed, "w", ZIP_DEFLATED) as rewritten:
        for info in archive.infolist():
            data = archive.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                data = data[:-20]
            rewritten.writestr(info, data)
    with pytest.raises(UploadValidationError, match="không thể đọc"):
        parse("malformed.xlsx", malformed.getvalue())


def test_xlsx_rejects_unknown_sheet_and_non_xlsx_archive() -> None:
    content = xlsx_bytes([["Tên"], ["A"]])
    with pytest.raises(UploadValidationError, match="không tồn tại"):
        parse("report.xlsx", content, sheet_name="Missing")
    with pytest.raises(UploadValidationError, match="archive"):
        parse("report.xlsx", b"not-a-zip")


def test_filename_is_reduced_to_basename_and_unsupported_types_are_rejected() -> None:
    parsed = parse("../../safe.csv", b"name\nvalue\n")
    assert parsed.filename == "safe.csv"
    with pytest.raises(UploadValidationError, match="CSV hoặc XLSX"):
        parse("payload.xlsm", b"content")
