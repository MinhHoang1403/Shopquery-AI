"""PostgreSQL persistence for dataset workspaces and their tabular sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid4

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
    delete,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ResourceConflictError, ResourceNotFoundError
from app.database.models import ChatConversation, Dataset, DatasetTable
from app.database.quotas import enforce_storage_budget, lock_owner_budget
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
    "TIMESTAMPTZ": partial(TIMESTAMP, timezone=True),
}


@dataclass(frozen=True)
class DatasetTableInfo:
    display_name: str
    sheet_name: str | None
    physical_table_name: str
    columns: tuple[ColumnSpec, ...]
    row_count: int
    dataset_table_id: int | None = None
    original_filename: str | None = None
    file_type: str | None = None


@dataclass(frozen=True)
class DatasetInfo:
    dataset_id: int
    name: str
    original_filename: str | None
    file_type: str | None
    row_count: int | None
    column_count: int | None
    created_at: datetime
    table: DatasetTableInfo | None
    tables: tuple[DatasetTableInfo, ...] = ()
    document_count: int = 0
    owner_user_id: UUID | None = None

    @property
    def table_count(self) -> int:
        return len(self.tables) if self.tables else int(self.table is not None)


class DatasetRepository:
    def __init__(self, setup_engine: Engine, readonly_engine: Engine, owner_user_id: UUID) -> None:
        if not isinstance(owner_user_id, UUID):
            raise ValueError("An authenticated owner is required")
        self._setup_engine = setup_engine
        self._readonly_engine = readonly_engine
        self._owner_user_id = owner_user_id

    def has_demo_data(self) -> bool:
        with self._readonly_engine.connect() as connection:
            return bool(
                connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM products) OR EXISTS (SELECT 1 FROM orders) "
                        "OR EXISTS (SELECT 1 FROM document_chunks WHERE dataset_id IS NULL)"
                    )
                )
            )

    def list(self) -> list[DatasetInfo]:
        statement = (
            select(Dataset)
            .where(Dataset.owner_user_id == self._owner_user_id)
            .options(selectinload(Dataset.tables), selectinload(Dataset.documents))
            .order_by(Dataset.created_at.desc(), Dataset.dataset_id.desc())
        )
        with Session(self._setup_engine) as session:
            return [self._to_info(item) for item in session.scalars(statement).unique()]

    def get(self, dataset_id: int) -> DatasetInfo:
        statement = (
            select(Dataset)
            .options(selectinload(Dataset.tables), selectinload(Dataset.documents))
            .where(Dataset.dataset_id == dataset_id, Dataset.owner_user_id == self._owner_user_id)
        )
        with Session(self._setup_engine) as session:
            dataset = session.scalar(statement)
            info = self._to_info(dataset) if dataset is not None else None
        if info is None:
            raise ResourceNotFoundError("Không tìm thấy bộ dữ liệu.")
        return info

    def create_workspace(self, name: str) -> DatasetInfo:
        normalized_name = self._validate_name(name)
        try:
            with Session(self._setup_engine) as session:
                lock_owner_budget(session.connection(), self._owner_user_id)
                dataset = Dataset(name=normalized_name, owner_user_id=self._owner_user_id)
                session.add(dataset)
                session.flush()
                enforce_storage_budget(session.connection(), self._owner_user_id)
                session.commit()
                dataset_id = dataset.dataset_id
        except IntegrityError as exc:
            raise ResourceConflictError("Tên bộ dữ liệu đã tồn tại.") from exc
        return self.get(dataset_id)

    def create(self, name: str, parsed: ParsedTable) -> DatasetInfo:
        """Keep the legacy create-and-import flow atomic."""

        normalized_name = self._validate_name(name)
        physical_name = f"dataset_{uuid4().hex}"
        dynamic_table = self._table(physical_name, parsed.columns)
        display_name = parsed.sheet_name or PurePosixPath(parsed.filename).stem[:120]
        try:
            with self._setup_engine.begin() as connection:
                lock_owner_budget(connection, self._owner_user_id)
                dataset_id = connection.scalar(
                    insert(Dataset)
                    .values(
                        name=normalized_name,
                        owner_user_id=self._owner_user_id,
                        original_filename=parsed.filename,
                        file_type=parsed.file_type,
                        row_count=parsed.row_count,
                        column_count=parsed.column_count,
                    )
                    .returning(Dataset.dataset_id)
                )
                if dataset_id is None:
                    raise RuntimeError("Dataset insert did not return an identifier")
                self._insert_table(
                    connection,
                    dataset_id,
                    display_name,
                    physical_name,
                    parsed,
                    dynamic_table,
                )
                enforce_storage_budget(connection, self._owner_user_id)
        except IntegrityError as exc:
            raise ResourceConflictError("Tên bộ dữ liệu hoặc bảng đã tồn tại.") from exc
        return self.get(dataset_id)

    def add_table(
        self, dataset_id: int, parsed: ParsedTable, display_name: str | None = None
    ) -> DatasetInfo:
        self.get(dataset_id)
        name = (display_name or parsed.sheet_name or PurePosixPath(parsed.filename).stem).strip()
        if not name or len(name) > 120:
            raise ValueError("Tên bảng phải có từ 1 đến 120 ký tự.")
        physical_name = f"dataset_{uuid4().hex}"
        dynamic_table = self._table(physical_name, parsed.columns)
        try:
            with self._setup_engine.begin() as connection:
                lock_owner_budget(connection, self._owner_user_id)
                self._lock_dataset(connection, dataset_id)
                self._insert_table(
                    connection,
                    dataset_id,
                    name,
                    physical_name,
                    parsed,
                    dynamic_table,
                )
                enforce_storage_budget(connection, self._owner_user_id)
        except IntegrityError as exc:
            raise ResourceConflictError("Tên bảng đã tồn tại trong bộ dữ liệu.") from exc
        return self.get(dataset_id)

    def preview_rows(
        self, dataset_id: int, limit: int = 10, table_id: int | None = None
    ) -> list[dict[str, Any]]:
        dataset = self.get(dataset_id)
        table_info = self._select_table(dataset, table_id)
        table = self._table(table_info.physical_table_name, table_info.columns)
        with self._readonly_engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(select(table).limit(limit)).mappings()]
        source_names = {column.name: column.source_name for column in table_info.columns}
        return [
            {source_names[key]: _json_safe(value) for key, value in row.items()} for row in rows
        ]

    def delete_table(self, dataset_id: int, table_id: int) -> None:
        with self._setup_engine.begin() as connection:
            self._lock_dataset(connection, dataset_id)
            item = connection.execute(
                select(DatasetTable.physical_table_name).where(
                    DatasetTable.dataset_id == dataset_id,
                    DatasetTable.dataset_table_id == table_id,
                )
            ).scalar_one_or_none()
            if item is None:
                raise ResourceNotFoundError("Không tìm thấy bảng trong bộ dữ liệu.")
            self._table(item, ()).drop(connection)
            connection.execute(
                delete(DatasetTable).where(
                    DatasetTable.dataset_id == dataset_id,
                    DatasetTable.dataset_table_id == table_id,
                )
            )
            # Legacy import metadata must not describe a file that has been removed.
            connection.execute(
                update(Dataset)
                .where(Dataset.dataset_id == dataset_id)
                .values(original_filename=None, file_type=None, row_count=None, column_count=None)
            )

    def delete(self, dataset_id: int, *, delete_conversations: bool = False) -> None:
        """Remove only registered sources, atomically; never cascade a physical DROP."""

        with self._setup_engine.begin() as connection:
            self._lock_dataset(connection, dataset_id)
            conversation = connection.scalar(
                select(ChatConversation.conversation_id)
                .where(ChatConversation.dataset_id == dataset_id)
                .limit(1)
            )
            if conversation is not None and not delete_conversations:
                raise ResourceConflictError(
                    "Bộ dữ liệu có lịch sử chat. Hãy xác nhận xóa cả lịch sử liên quan "
                    "hoặc xóa các cuộc trò chuyện trước."
                )
            names = connection.scalars(
                select(DatasetTable.physical_table_name).where(
                    DatasetTable.dataset_id == dataset_id
                )
            ).all()
            for name in names:
                self._table(name, ()).drop(connection)
            if delete_conversations:
                connection.execute(
                    delete(ChatConversation).where(ChatConversation.dataset_id == dataset_id)
                )
            connection.execute(delete(Dataset).where(Dataset.dataset_id == dataset_id))

    def _lock_dataset(self, connection: Any, dataset_id: int) -> None:
        exists = connection.scalar(
            select(Dataset.dataset_id)
            .where(Dataset.dataset_id == dataset_id, Dataset.owner_user_id == self._owner_user_id)
            .with_for_update()
        )
        if exists is None:
            raise ResourceNotFoundError("Không tìm thấy bộ dữ liệu.")

    def categorical_values(
        self,
        dataset: DatasetInfo,
        *,
        max_distinct_values: int = 20,
        max_value_length: int = 80,
    ) -> dict[str, tuple[str, ...]] | dict[str, dict[str, tuple[str, ...]]]:
        """Return bounded exact values grouped by physical table name."""

        dataset = self.get(dataset.dataset_id)
        result: dict[str, dict[str, tuple[str, ...]]] = {}
        with self._readonly_engine.connect() as connection:
            for info in dataset.tables or (() if dataset.table is None else (dataset.table,)):
                table = self._table(info.physical_table_name, info.columns)
                hints: dict[str, tuple[str, ...]] = {}
                for column in info.columns:
                    if column.data_type != "TEXT":
                        continue
                    expression = table.c[column.name]
                    values = list(
                        connection.scalars(
                            select(expression)
                            .where(expression.is_not(None), expression != "")
                            .distinct()
                            .limit(max_distinct_values + 1)
                        )
                    )
                    if len(values) <= max_distinct_values and all(
                        len(value) <= max_value_length for value in values
                    ):
                        hints[column.name] = tuple(
                            sorted(values, key=lambda value: value.casefold())
                        )
                result[info.physical_table_name] = hints
        if len(result) == 1:
            return next(iter(result.values()))
        return result

    def _insert_table(
        self,
        connection: Any,
        dataset_id: int,
        display_name: str,
        physical_name: str,
        parsed: ParsedTable,
        dynamic_table: Table,
    ) -> None:
        dynamic_table.create(connection)
        if parsed.rows:
            connection.execute(insert(dynamic_table), parsed.database_rows())
        connection.execute(
            insert(DatasetTable).values(
                dataset_id=dataset_id,
                display_name=display_name,
                original_filename=parsed.filename,
                file_type=parsed.file_type,
                sheet_name=parsed.sheet_name,
                physical_table_name=physical_name,
                columns=[column.as_dict() for column in parsed.columns],
                row_count=parsed.row_count,
            )
        )
        connection.execute(
            text(f'GRANT SELECT ON TABLE "{UPLOADED_SCHEMA}"."{physical_name}" TO shopquery_reader')
        )

    @staticmethod
    def _select_table(dataset: DatasetInfo, table_id: int | None) -> DatasetTableInfo:
        tables = dataset.tables or (() if dataset.table is None else (dataset.table,))
        if not tables:
            raise ResourceNotFoundError("Bộ dữ liệu chưa có bảng dữ liệu.")
        if table_id is None:
            return tables[0]
        for item in tables:
            if item.dataset_table_id == table_id:
                return item
        raise ResourceNotFoundError("Không tìm thấy bảng trong bộ dữ liệu.")

    @staticmethod
    def _validate_name(name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Tên bộ dữ liệu không được để trống.")
        if len(normalized) > 120:
            raise ValueError("Tên bộ dữ liệu không được vượt quá 120 ký tự.")
        return normalized

    @staticmethod
    def _table(name: str, columns: tuple[ColumnSpec, ...]) -> Table:
        return Table(
            name,
            MetaData(),
            *[
                Column(column.name, SQL_TYPES[column.data_type](), nullable=True)
                for column in columns
            ],
            schema=UPLOADED_SCHEMA,
        )

    @staticmethod
    def _to_info(dataset: Dataset) -> DatasetInfo:
        tables = tuple(
            DatasetTableInfo(
                dataset_table_id=table.dataset_table_id,
                display_name=table.display_name,
                original_filename=table.original_filename,
                file_type=table.file_type,
                sheet_name=table.sheet_name,
                physical_table_name=table.physical_table_name,
                columns=tuple(ColumnSpec(**column) for column in table.columns),
                row_count=table.row_count,
            )
            for table in sorted(dataset.tables, key=lambda item: item.dataset_table_id)
        )
        first = tables[0] if tables else None
        return DatasetInfo(
            dataset_id=dataset.dataset_id,
            name=dataset.name,
            original_filename=(
                dataset.original_filename or (first.original_filename if first else None)
            ),
            file_type=dataset.file_type or (first.file_type if first else None),
            row_count=dataset.row_count
            if dataset.row_count is not None
            else (first.row_count if first else None),
            column_count=dataset.column_count
            if dataset.column_count is not None
            else (len(first.columns) if first else None),
            created_at=dataset.created_at,
            table=first,
            tables=tables,
            document_count=len(dataset.documents),
            owner_user_id=dataset.owner_user_id,
        )
