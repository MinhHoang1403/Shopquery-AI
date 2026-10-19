"""Enforce storage budgets inside the same transaction that adds user data."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Connection, func, select, text

from app.core.config import get_settings
from app.database.models import Dataset, DatasetTable, DocumentChunk


def lock_owner_budget(connection: Connection, owner: UUID) -> None:
    connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": owner.int % (2**63 - 1)})


def storage_usage(connection: Connection, owner: UUID) -> tuple[int, int]:
    count = (
        connection.scalar(
            select(func.count()).select_from(Dataset).where(Dataset.owner_user_id == owner)
        )
        or 0
    )
    names = connection.scalars(
        select(DatasetTable.physical_table_name).join(Dataset).where(Dataset.owner_user_id == owner)
    ).all()
    size = sum(
        connection.scalar(
            text("SELECT pg_total_relation_size(to_regclass(:name))"),
            {"name": f"uploaded_data.{name}"},
        )
        or 0
        for name in names
    )
    size += (
        connection.scalar(
            select(func.coalesce(func.sum(func.octet_length(DocumentChunk.content) + 768 * 4), 0))
            .join(Dataset, Dataset.dataset_id == DocumentChunk.dataset_id)
            .where(Dataset.owner_user_id == owner)
        )
        or 0
    )
    return count, size


def enforce_storage_budget(connection: Connection, owner: UUID) -> None:
    settings = get_settings()
    count, size = storage_usage(connection, owner)
    if count > settings.beta_max_datasets or size > settings.beta_max_user_bytes:
        raise HTTPException(429, "Đã đạt giới hạn workspace hoặc dung lượng dữ liệu beta.")
