"""Synthetic schema-width characterization; optional, bounded provider checks."""

import csv
import io
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine
from sqlalchemy.schema import CreateSchema

from app.ai.providers import build_generation_gateway
from app.core.config import Settings
from app.core.errors import SqlValidationError, UploadValidationError
from app.database.test_safety import require_test_database
from app.datasets.context import DatasetSqlContext, build_dataset_sql_context
from app.datasets.parser import ParsedTable, parse_tabular_file
from app.datasets.repository import SQL_TYPES, DatasetInfo, DatasetTableInfo
from app.routing.router import QueryRouter, RouteLabel
from app.text_to_sql.compiler import QueryCompiler
from app.text_to_sql.executor import SqlExecutor, _json_safe
from app.text_to_sql.planner import QueryPlanner
from app.text_to_sql.validator import SqlValidator

WIDTHS = (5, 15, 30)
QUESTION = (
    "Trong tháng 9/2026 theo cột Ngày ghi nhận, nhóm theo Nhóm, tính tổng cột Số tiền "
    "(không phải So tien hoặc Số tiền dự kiến). Trả về nhom, tong_tien, so_dong "
    "(COUNT tất cả dòng), so_gia_tri (COUNT Số tiền không NULL). Giữ NULL khác 0."
)


def wide_table(width: int) -> ParsedTable:
    headers = ["Mã bản ghi", "Nhóm", "Số tiền", "Ngày ghi nhận", "Giá trị kèm đơn vị"]
    extras = [
        "So tien",
        "Số tiền dự kiến",
        "Ngày cập nhật",
        "Lần ghi nhận",
        "Toàn NULL",
        "Trạng thái",
        "Nhãn",
        "Mã số 0 đầu",
        "Nợ học phí",
        "Đã đóng",
    ] + [f"Thông số {index:02}" for index in range(1, 16)]
    headers += extras[: width - 5]
    base = [
        ["001", "Lớp A", "10.25", "2026-09-01", "10 kWh"],
        ["002", "Lớp A", None, "2026-09-30", "2 kWh"],
        ["003", "Lớp B", "20.50", "2026-09-15", "5 kWh"],
        ["004", "Lớp B", "0.00", "2026-10-01", "0 kWh"],
        ["005", "Lớp C", None, "2026-09-20", None],
        ["006", "Lớp D", "0.00", "2026-09-20", "0 kWh"],
    ]
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for index, row in enumerate(base):
        values = [
            "999.99",
            "888.88",
            "2026-09-30T23:30:00+07:00",
            str(index % 2),
            None,
            "Đã xác nhận",
            "giả lập",
            f"00{index}",
            "100.50",
            "50.25",
        ] + [str(index + 2) for _ in range(15)]
        writer.writerow(row + values[: width - 5])
    return parse_tabular_file(
        f"wide_{width}.csv",
        output.getvalue().encode(),
        max_bytes=10 * 1024 * 1024,
        max_rows=5000,
        max_columns=30,
    )


def wide_context(parsed: ParsedTable) -> DatasetSqlContext:
    table = DatasetTableInfo(
        "Bảng giả lập",
        None,
        f"wide_{parsed.column_count}",
        parsed.columns,
        parsed.row_count,
        original_filename=parsed.filename,
    )
    return build_dataset_sql_context(
        DatasetInfo(
            1,
            "Audit synthetic",
            None,
            None,
            None,
            None,
            datetime(2026, 10, 19, tzinfo=UTC),
            table,
        )
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_full_schema_preserves_every_header_type_and_allowed_column(width: int) -> None:
    parsed = wide_table(width)
    context = wide_context(parsed)
    assert parsed.column_count == width
    assert parsed.row_count == 6
    assert len(context.table_columns[f"wide_{width}"]) == width
    for column in parsed.columns:
        assert f'{column.name} {column.data_type} (source header: "{column.source_name}")' in (
            context.schema_context
        )
    assert parsed.columns[2].data_type == "NUMERIC"
    assert parsed.columns[3].data_type == "DATE"
    assert parsed.columns[4].data_type == "TEXT"
    assert parsed.database_rows()[1]["so_tien"] is None
    assert parsed.database_rows()[5]["so_tien"] == Decimal("0")
    if width >= 15:
        assert parsed.columns[5].name == "so_tien_2"
        assert parsed.columns[7].data_type == "TIMESTAMPTZ"
        assert parsed.columns[8].data_type == "BOOLEAN"
        assert parsed.columns[9].data_type == "TEXT"
        assert parsed.database_rows()[0]["ngay_cap_nhat"].utcoffset().total_seconds() == 25200
    print(
        json.dumps(
            {
                "columns": width,
                "schema_chars": len(context.schema_context),
                "schema_bytes": len(context.schema_context.encode()),
            }
        )
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_wide_schema_rejects_missing_fields_other_tables_joins_and_writes(width: int) -> None:
    context = wide_context(wide_table(width))
    validator = SqlValidator(context.table_columns, context.allowed_schemas, max_tables=1)
    table = f"uploaded_data.wide_{width}"
    validator.validate(f"SELECT nhom, SUM(so_tien), COUNT(*) FROM {table} GROUP BY nhom")
    for sql in (
        f"SELECT salary FROM {table}",
        "SELECT * FROM uploaded_data.someone_else",
        f"SELECT a.nhom FROM {table} a JOIN {table} b ON a.nhom=b.nhom",
        f"DELETE FROM {table}",
        f"UPDATE {table} SET so_tien=0",
    ):
        with pytest.raises(SqlValidationError):
            validator.validate(sql)


def test_parser_rejects_31_columns_at_current_upload_limit() -> None:
    with pytest.raises(UploadValidationError):
        parse_tabular_file(
            "wide.csv",
            (
                ",".join(f"c{i}" for i in range(31)) + "\n" + ",".join("2" for _ in range(31))
            ).encode(),
            max_bytes=1024,
            max_rows=5000,
            max_columns=30,
        )


def test_timestamp_mapping_and_binary_numeric_inference_are_explicit_characterizations() -> None:
    parsed = wide_table(15)
    assert SQL_TYPES["TIMESTAMP"]().timezone is False
    assert SQL_TYPES["TIMESTAMPTZ"]().timezone is True
    assert parsed.columns[8].data_type == "BOOLEAN"
    assert parsed.columns[9].data_type == "TEXT"


def test_large_decimal_json_conversion_is_lossless() -> None:
    original = Decimal("12345678901234567890.12")
    converted = _json_safe(original)
    assert isinstance(converted, str)
    assert Decimal(converted) == original


def test_projection_alias_cannot_bypass_unknown_unqualified_column_validation() -> None:
    context = wide_context(wide_table(30))
    validator = SqlValidator(context.table_columns, context.allowed_schemas, max_tables=1)
    with pytest.raises(SqlValidationError):
        validator.validate("SELECT salary AS salary FROM uploaded_data.wide_30")


@pytest.mark.live
@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
@pytest.mark.parametrize("width", WIDTHS)
def test_live_wide_group_by_against_disposable_postgres(width: int, model: str) -> None:
    if os.getenv("RUN_SQL_SCHEMA_LIVE_AUDIT") != "1":
        pytest.skip("Explicit synthetic-provider audit opt-in required")
    url = os.environ["SHOPQUERY_TEST_DATABASE_URL"]
    require_test_database(url)
    settings = Settings()
    assert settings.beta_provider_data_enabled
    parsed = wide_table(width)
    context = wide_context(parsed)
    engine = create_engine(url)
    metadata = MetaData(schema="uploaded_data")
    table = Table(
        f"wide_{width}",
        metadata,
        *(Column(c.name, SQL_TYPES[c.data_type]()) for c in parsed.columns),
    )
    gateway = build_generation_gateway(settings, model)
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema("uploaded_data", if_not_exists=True))
            table.create(connection)
            connection.execute(table.insert(), parsed.database_rows())
        started = perf_counter()
        plan = QueryPlanner(gateway, settings.demo_reference_date, context).generate(QUESTION)
        generated = perf_counter()
        compiled = QueryCompiler(context).compile(plan)
        checked = perf_counter()
        rows = SqlExecutor(engine, 5000, 200).execute(compiled.validated, compiled.parameters)
        finished = perf_counter()
        assert sorted(rows, key=lambda row: row["nhom"]) == [
            {"nhom": "Lớp A", "tong_tien": "10.25", "so_dong": 2, "so_gia_tri": 1},
            {"nhom": "Lớp B", "tong_tien": "20.50", "so_dong": 1, "so_gia_tri": 1},
            {"nhom": "Lớp C", "tong_tien": None, "so_dong": 1, "so_gia_tri": 0},
            {"nhom": "Lớp D", "tong_tien": "0.00", "so_dong": 1, "so_gia_tri": 1},
        ]
        print(
            json.dumps(
                {
                    "model": model,
                    "columns": width,
                    "schema_chars": len(context.schema_context),
                    "generation_ms": round((generated - started) * 1000, 2),
                    "validation_ms": round((checked - generated) * 1000, 2),
                    "execution_ms": round((finished - checked) * 1000, 2),
                    "logical_generation_calls": 1,
                    "tokens": "unknown (not exposed by gateway)",
                    "validated_sql": compiled.evidence_sql,
                },
                ensure_ascii=False,
            )
        )
    finally:
        gateway.close()
        metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.live
@pytest.mark.parametrize("model", ["inetcloud-knowledge", "gemini"])
def test_live_router_rejects_a_missing_column_in_30_column_schema(model: str) -> None:
    if os.getenv("RUN_SQL_SCHEMA_LIVE_AUDIT") != "1":
        pytest.skip("Explicit synthetic-provider audit opt-in required")
    settings = Settings()
    assert settings.beta_provider_data_enabled
    gateway = build_generation_gateway(settings, model)
    context = wide_context(wide_table(30))
    try:
        started = perf_counter()
        decision = QueryRouter(gateway, context.routing_context).route(
            "Tính tuổi trung bình của người dùng, cần ngày sinh. Bảng có ngày sinh không?",
            frozenset({RouteLabel.SQL, RouteLabel.UNSUPPORTED}),
        )
        print(
            json.dumps(
                {
                    "model": model,
                    "case": "missing_date_of_birth",
                    "route": decision.route,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                },
                ensure_ascii=False,
            )
        )
        assert decision.route == RouteLabel.UNSUPPORTED
    finally:
        gateway.close()
