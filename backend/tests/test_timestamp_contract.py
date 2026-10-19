"""Import timestamps without guessing or discarding their timezone semantics."""

from datetime import date, datetime, timedelta

import pytest

from app.core.errors import UploadValidationError
from app.datasets.repository import SQL_TYPES
from tests.test_dataset_parser import parse, xlsx_bytes


@pytest.mark.parametrize(
    ("value", "data_type", "offset"),
    [
        ("2026-10-01", "DATE", None),
        ("2026-10-01T00:30:00", "TIMESTAMP", None),
        ("2026-10-01T00:30:00+07:00", "TIMESTAMPTZ", timedelta(hours=7)),
        ("2026-09-30T17:30:00Z", "TIMESTAMPTZ", timedelta(0)),
        ("2026-09-30T13:30:00-04:00", "TIMESTAMPTZ", timedelta(hours=-4)),
    ],
)
def test_csv_temporal_contract(value: str, data_type: str, offset: timedelta | None) -> None:
    parsed = parse("times.csv", f"Thời điểm\n{value}\n".encode())
    assert parsed.columns[0].data_type == data_type
    stored = parsed.database_rows()[0]["thoi_diem"]
    if data_type == "DATE":
        assert type(stored) is date
    else:
        assert isinstance(stored, datetime)
        assert stored.utcoffset() == offset
        assert SQL_TYPES[data_type]().timezone == (offset is not None)


@pytest.mark.parametrize(
    "values",
    [
        ["2026-10-01T00:30:00+07:00", "2026-10-01T00:30:00"],
        ["2026-10-01T00:30:00Z", "2026-10-01"],
        ["2026-10-01", "2026-10-01T00:30:00"],
    ],
)
@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_mixed_temporal_contract_is_rejected(values: list[str], format: str) -> None:
    content = (
        ("Thời điểm\n" + "\n".join(values)).encode()
        if format == "csv"
        else xlsx_bytes([["Thời điểm"], *[[value] for value in values]])
    )
    with pytest.raises(UploadValidationError, match="Thời điểm.*trộn"):
        parse(f"mixed.{format}", content)


def test_xlsx_native_date_naive_datetime_and_offset_text_are_distinct() -> None:
    parsed = parse(
        "times.xlsx",
        xlsx_bytes(
            [
                ["Ngày", "Giờ", "Instant"],
                [date(2026, 10, 1), datetime(2026, 10, 1, 0, 30), "2026-10-01T00:30:00+07:00"],
            ]
        ),
    )
    assert [column.data_type for column in parsed.columns] == ["DATE", "TIMESTAMP", "TIMESTAMPTZ"]
    row = parsed.database_rows()[0]
    assert type(row["ngay"]) is date
    assert row["gio"].tzinfo is None
    assert row["instant"].utcoffset() == timedelta(hours=7)


@pytest.mark.parametrize("value", ["2026-02-30", "2026-10-01T25:30:00+07:00"])
def test_invalid_temporal_values_have_upload_errors(value: str) -> None:
    with pytest.raises(UploadValidationError, match="Thời điểm"):
        parse("invalid.csv", f"Thời điểm\n{value}\n".encode())
