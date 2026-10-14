"""Offline validation for bounded CSV and XLSX parsing."""

from io import BytesIO

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
