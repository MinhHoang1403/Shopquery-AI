"""PostgreSQL persistence for managed uploaded datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BIGINT,
    BOOLEAN,
    DATE,
    NUMERIC,
    TIMESTAMP,
    Column,
    Engine,
    MetaData,
    String,
    Table,
    func,
    insert,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ResourceConflictError, ResourceNotFoundError
from app.database.models import Dataset, DatasetTable
from app.datasets.parser import ColumnSpec, ParsedTable
from app.text_to_sql.executor import _json_safe

UPLOADED_SCHEMA = "uploaded_data"
SQL_TYPES = {
    "TEXT": String,
    "BIGINT": BIGINT,
    "NUMERIC": NUMERIC,
    "BOOLEAN": BOOLEAN,
    "DATE": DATE,
    "TIMESTAMP": TIMESTAMP,
}


@dataclass(frozen=True)
class DatasetTableInfo:
    display_name: str
    sheet_name: str | None
    physical_table_name: str
    columns: tuple[ColumnSpec, ...]
    row_count: int


@dataclass(frozen=True)
class DatasetInfo:
    dataset_id: int
    name: str
    original_filename: str
    file_type: str
    row_count: int
    column_count: int
    created_at: datetime
    table: DatasetTableInfo


class DatasetRepository:
    def __init__(self, setup_engine: Engine, readonly_engine: Engine) -> None:
        self._setup_engine = setup_engine
        self._readonly_engine = readonly_engine

    def list(self) -> list[DatasetInfo]:
        statement = (
            select(Dataset, DatasetTable)
            .join(DatasetTable, DatasetTable.dataset_id == Dataset.dataset_id)
            .order_by(Dataset.created_at.desc(), Dataset.dataset_id.desc())
        )
        with Session(self._setup_engine) as session:
            return [
                self._to_info(dataset, table)
                for dataset, table in session.execute(statement)
            ]

    def get(self, dataset_id: int) -> DatasetInfo:
        statement = (
            select(Dataset, DatasetTable)
            .join(DatasetTable, DatasetTable.dataset_id == Dataset.dataset_id)
            .where(Dataset.dataset_id == dataset_id)
        )
        with Session(self._setup_engine) as session:
            row = session.execute(statement).first()
        if row is None:
            raise ResourceNotFoundError("Không tìm thấy bộ dữ liệu.")
        return self._to_info(row[0], row[1])

    def create(self, name: str, parsed: ParsedTable) -> DatasetInfo:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Tên bộ dữ liệu không được để trống.")
        if len(normalized_name) > 120:
            raise ValueError("Tên bộ dữ liệu không được vượt quá 120 ký tự.")

        physical_table_name = f"dataset_{uuid4().hex}"
        dynamic_table = self._table(physical_table_name, parsed.columns)
        filename_stem = PurePosixPath(parsed.filename).stem[:120]
        try:
            with self._setup_engine.begin() as connection:
                existing = connection.scalar(
                    select(Dataset.dataset_id).where(
                        func.lower(Dataset.name) == normalized_name.lower()
                    )
                )
                if existing is not None:
                    raise ResourceConflictError("Tên bộ dữ liệu đã tồn tại.")
                dataset_id = connection.scalar(
                    insert(Dataset)
                    .values(
                        name=normalized_name,
                        original_filename=parsed.filename,
                        file_type=parsed.file_type,
                        row_count=parsed.row_count,
                        column_count=parsed.column_count,
                    )
                    .returning(Dataset.dataset_id)
                )
                if dataset_id is None:
                    raise RuntimeError("Dataset insert did not return an identifier")
                dynamic_table.create(connection)
                if parsed.rows:
                    connection.execute(insert(dynamic_table), parsed.database_rows())
                connection.execute(
                    insert(DatasetTable).values(
                        dataset_id=dataset_id,
                        display_name=parsed.sheet_name or filename_stem,
                        sheet_name=parsed.sheet_name,
                        physical_table_name=physical_table_name,
                        columns=[column.as_dict() for column in parsed.columns],
                        row_count=parsed.row_count,
                    )
                )
                connection.execute(
                    text(
                        f'GRANT SELECT ON TABLE "{UPLOADED_SCHEMA}".'
                        f'"{physical_table_name}" TO shopquery_reader'
                    )
                )
        except IntegrityError as exc:
            raise ResourceConflictError("Tên bộ dữ liệu đã tồn tại.") from exc
        return self.get(dataset_id)

    def preview_rows(self, dataset_id: int, limit: int = 10) -> list[dict[str, Any]]:
        dataset = self.get(dataset_id)
        table = self._table(dataset.table.physical_table_name, dataset.table.columns)
        with self._readonly_engine.connect() as connection:
            result = connection.execute(select(table).limit(limit)).mappings()
            rows = [dict(row) for row in result]
        source_names = {column.name: column.source_name for column in dataset.table.columns}
        return [
            {source_names[key]: _json_safe(value) for key, value in row.items()}
            for row in rows
        ]

    @staticmethod
    def _table(name: str, columns: tuple[ColumnSpec, ...]) -> Table:
        metadata = MetaData()
        return Table(
            name,
            metadata,
            *[
                Column(column.name, SQL_TYPES[column.data_type](), nullable=True)
                for column in columns
            ],
            schema=UPLOADED_SCHEMA,
        )

    @staticmethod
    def _to_info(dataset: Any, table: Any) -> DatasetInfo:
        columns = tuple(ColumnSpec(**column) for column in table.columns)
        return DatasetInfo(
            dataset_id=dataset.dataset_id,
            name=dataset.name,
            original_filename=dataset.original_filename,
            file_type=dataset.file_type,
            row_count=dataset.row_count,
            column_count=dataset.column_count,
            created_at=dataset.created_at,
            table=DatasetTableInfo(
                display_name=table.display_name,
                sheet_name=table.sheet_name,
                physical_table_name=table.physical_table_name,
                columns=columns,
                row_count=table.row_count,
            ),
        )
