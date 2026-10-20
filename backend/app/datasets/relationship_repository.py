"""Owner-scoped confirmation and execution-time validation for immutable uploads."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, insert, select, text
from sqlalchemy.orm import Session

from app.core.errors import ConfigurationError, ResourceConflictError, ResourceNotFoundError
from app.database.models import Dataset, DatasetRelationship, DatasetTable
from app.datasets.parser import ColumnSpec
from app.datasets.relationship_detection import detect_relationships
from app.datasets.relationships import (
    MAX_RELATIONSHIPS,
    RelationshipConfirm,
    RelationshipInput,
    RelationshipPreview,
    RelationshipRecord,
    RelationshipTable,
    relationship_revision,
    relationship_tables,
    verify_relationship,
)
from app.text_to_sql.join_policy import ApprovedJoin
from app.text_to_sql.validator import ValidatedSql


class RelationshipRepository:
    def __init__(self, engine: Engine, owner_user_id: UUID) -> None:
        if not isinstance(owner_user_id, UUID):
            raise ValueError("An authenticated owner is required")
        self.engine, self.owner = engine, owner_user_id

    @contextmanager
    def _session(self, dataset_id: int, *, shared: bool = False) -> Iterator[Session]:
        with Session(self.engine) as session, session.begin():
            session.execute(text("SET LOCAL lock_timeout='3s'"))
            session.execute(text("SET LOCAL statement_timeout='5s'"))
            dataset = session.scalar(
                select(Dataset)
                .where(
                    Dataset.dataset_id == dataset_id,
                    Dataset.owner_user_id == self.owner,
                )
                .with_for_update(read=shared)
            )
            if dataset is None:
                raise ResourceNotFoundError("Không tìm thấy workspace.")
            if not session.scalar(text("SELECT to_regclass('public.dataset_relationships')")):
                raise ConfigurationError("JOIN v1 chưa được migrate; cần quản trị viên phê duyệt.")
            yield session

    @staticmethod
    def _tables(session: Session | Connection, dataset_id: int) -> dict[str, RelationshipTable]:
        return {
            str(row["dataset_table_id"]): RelationshipTable(
                str(row["dataset_table_id"]),
                row["physical_table_name"],
                tuple(ColumnSpec(**col) for col in row["columns"]),
                row["row_count"],
                display_name=row["display_name"],
            )
            for row in session.execute(
                select(DatasetTable.__table__).where(DatasetTable.dataset_id == dataset_id)
            ).mappings()
        }

    @staticmethod
    def detect_on_upload(connection: Connection, dataset_id: int, new_table_id: int) -> None:
        """Called inside the owner-locked upload transaction, never from model output."""
        connection.execute(text("SET LOCAL statement_timeout='5s'"))
        tables = RelationshipRepository._tables(connection, dataset_id)
        existing = list(
            connection.execute(
                select(
                    DatasetRelationship.source_table_id, DatasetRelationship.target_table_id
                ).where(DatasetRelationship.dataset_id == dataset_id)
            )
        )
        if len(existing) >= MAX_RELATIONSHIPS:
            return
        previews = detect_relationships(
            connection,
            tables,
            str(new_table_id),
            {
                frozenset({str(item.source_table_id), str(item.target_table_id)})
                for item in existing
            },
        )
        if len(existing) + len(previews) > MAX_RELATIONSHIPS:
            return
        for preview in previews:
            record = RelationshipRecord(
                **preview.model_dump(),
                relationship_id=str(uuid4()),
                origin="automatic",
                confirmed=False,
            )
            connection.execute(
                insert(DatasetRelationship).values(
                    relationship_id=UUID(record.relationship_id),
                    dataset_id=dataset_id,
                    source_table_id=int(record.source_table_id),
                    source_column=record.source_column,
                    target_table_id=int(record.target_table_id),
                    target_column=record.target_column,
                    revision=record.revision,
                    statistics=record.model_dump(exclude={"relationship_id"}),
                )
            )

    def preview(self, dataset_id: int, request: RelationshipInput) -> RelationshipPreview:
        with self._session(dataset_id, shared=True) as session:
            return verify_relationship(
                session.connection(), request, self._tables(session, dataset_id)
            )

    def confirm(self, dataset_id: int, request: RelationshipConfirm) -> RelationshipRecord:
        with self._session(dataset_id) as session:
            preview = verify_relationship(
                session.connection(), request, self._tables(session, dataset_id)
            )
            if request.revision != preview.revision:
                raise ResourceConflictError("Nguồn đã thay đổi; hãy kiểm tra quan hệ lại.")
            if not preview.valid:
                raise ResourceConflictError(" ".join(preview.reasons))
            items = list(
                session.scalars(
                    select(DatasetRelationship).where(
                        DatasetRelationship.dataset_id == dataset_id,
                    )
                )
            )
            existing = next(
                (
                    item
                    for item in items
                    if (
                        str(item.source_table_id),
                        item.source_column,
                        str(item.target_table_id),
                        item.target_column,
                    )
                    == (
                        request.source_table_id,
                        request.source_column,
                        request.target_table_id,
                        request.target_column,
                    )
                ),
                None,
            )
            if existing is None:
                if len(items) >= MAX_RELATIONSHIPS:
                    raise ResourceConflictError("Workspace đã đạt giới hạn 20 liên kết.")
                existing = DatasetRelationship(
                    relationship_id=uuid4(),
                    dataset_id=dataset_id,
                    source_table_id=int(request.source_table_id),
                    source_column=request.source_column,
                    target_table_id=int(request.target_table_id),
                    target_column=request.target_column,
                )
                session.add(existing)
            existing.revision, existing.statistics = preview.revision, preview.model_dump()
            session.flush()
            return RelationshipRecord(
                **preview.model_dump(), relationship_id=str(existing.relationship_id)
            )

    def list(self, dataset_id: int) -> list[RelationshipRecord]:
        with self._session(dataset_id, shared=True) as session:
            tables = self._tables(session, dataset_id)
            return self._records(session, dataset_id, tables)

    @staticmethod
    def _records(
        session: Session, dataset_id: int, tables: dict[str, RelationshipTable]
    ) -> list[RelationshipRecord]:
        result = []
        for item in session.scalars(
            select(DatasetRelationship)
            .where(
                DatasetRelationship.dataset_id == dataset_id,
            )
            .order_by(DatasetRelationship.created_at, DatasetRelationship.relationship_id)
        ):
            record = RelationshipRecord(
                **item.statistics, relationship_id=str(item.relationship_id)
            )
            try:
                current = relationship_revision(record, tables)
            except ResourceNotFoundError:
                current = None
            if current != item.revision or record.revision != item.revision:
                record = record.model_copy(
                    update={
                        "valid": False,
                        "cardinality": None,
                        "reasons": ["Nguồn đã thay đổi; cần kiểm tra và xác nhận lại liên kết."],
                    }
                )
            result.append(record)
        return result

    def approved(self, dataset_id: int) -> tuple[ApprovedJoin, ...]:
        with self._session(dataset_id, shared=True) as session:
            tables = self._tables(session, dataset_id)
            records = self._records(session, dataset_id, tables)
            result = []
            for record in records:
                if not record.valid or record.revision != relationship_revision(record, tables):
                    continue
                source, target = relationship_tables(record, tables)
                result.append(
                    ApprovedJoin(
                        record.relationship_id,
                        source.physical_name,
                        record.source_column,
                        target.physical_name,
                        record.target_column,
                        record.revision,
                    )
                )
            return tuple(result)

    def delete(self, dataset_id: int, relationship_id: UUID) -> None:
        with self._session(dataset_id) as session:
            item = session.scalar(
                select(DatasetRelationship).where(
                    DatasetRelationship.dataset_id == dataset_id,
                    DatasetRelationship.relationship_id == relationship_id,
                )
            )
            if item is None:
                raise ResourceNotFoundError("Không tìm thấy liên kết trong workspace.")
            session.delete(item)

    @contextmanager
    def execution_guard(
        self,
        dataset_id: int,
        approved: tuple[ApprovedJoin, ...],
        sql: ValidatedSql,
    ) -> Iterator[None]:
        ids = sql.relationship_ids or ((sql.relationship_id,) if sql.relationship_id else ())
        if not ids:
            yield
            return
        expected = {r.relationship_id: r for r in approved if r.relationship_id in ids}
        if len(ids) > 2 or len(set(ids)) != len(ids) or set(expected) != set(ids):
            raise ResourceConflictError("Liên kết chưa được duyệt trong request này.")
        with self._session(dataset_id, shared=True) as session:
            tables = self._tables(session, dataset_id)
            for relationship_id in ids:
                relation = expected[relationship_id]
                item = session.scalar(
                    select(DatasetRelationship).where(
                        DatasetRelationship.dataset_id == dataset_id,
                        DatasetRelationship.relationship_id == UUID(relationship_id),
                    )
                )
                if item is None or item.revision != relation.revision:
                    raise ResourceConflictError("Liên kết đã bị xóa/thay đổi. Hãy hỏi lại.")
                record = RelationshipRecord(
                    **item.statistics, relationship_id=str(item.relationship_id)
                )
                if (
                    not record.valid
                    or record.revision != relation.revision
                    or relationship_revision(record, tables) != relation.revision
                ):
                    raise ResourceConflictError("Nguồn liên kết đã thay đổi. Hãy xác nhận lại.")
            yield
