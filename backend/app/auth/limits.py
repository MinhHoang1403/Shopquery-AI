"""Small beta limits shared by API workers through PostgreSQL."""

import hashlib
import math
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.config import Settings, get_settings
from app.database.models import ResourceLease, ResourceLimit
from app.database.quotas import storage_usage
from app.database.session import get_setup_engine


class ResourceControl:
    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine, self.settings = engine, settings

    def rate(self, key: str, limit: int) -> None:
        now = datetime.now(UTC)
        bucket = f"{key}:{int(now.timestamp()) // 3600}"
        with self.engine.begin() as connection:
            connection.execute(delete(ResourceLimit).where(ResourceLimit.expires_at < now))
            statement = insert(ResourceLimit).values(
                key=bucket, count=1, expires_at=now + timedelta(hours=2)
            )
            count = connection.scalar(
                statement.on_conflict_do_update(
                    index_elements=[ResourceLimit.key],
                    set_={"count": ResourceLimit.count + 1},
                    where=ResourceLimit.count < limit,
                ).returning(ResourceLimit.count)
            )
        if count is None:
            raise HTTPException(
                429,
                "Đã vượt giới hạn yêu cầu beta. Vui lòng thử lại sau.",
                headers={"Retry-After": str(math.ceil(3600 - now.timestamp() % 3600))},
            )

    def login(self, ip: str) -> None:
        self.rate(
            "login:" + hashlib.sha256(ip.encode()).hexdigest(), self.settings.beta_login_per_ip_hour
        )

    @contextmanager
    def work(self, user_id: UUID, kind: str) -> Iterator[None]:
        settings = self.settings
        limit = (
            settings.beta_chat_per_user_hour
            if kind == "chat"
            else settings.beta_preview_per_user_hour
            if kind == "preview"
            else settings.beta_upload_per_user_hour
        )
        self.rate(f"{kind}:{user_id}", limit)
        lease_id, now = uuid4(), datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(71948103)"))
            connection.execute(delete(ResourceLease).where(ResourceLease.expires_at < now))
            total = connection.scalar(select(func.count()).select_from(ResourceLease))
            own = connection.scalar(
                select(func.count())
                .select_from(ResourceLease)
                .where(ResourceLease.user_id == user_id)
            )
            if total >= settings.beta_system_concurrency or own >= settings.beta_user_concurrency:
                raise HTTPException(429, "Hệ thống hoặc tài khoản đang có tác vụ xử lý.")
            connection.execute(
                insert(ResourceLease).values(
                    lease_id=lease_id,
                    user_id=user_id,
                    kind=kind,
                    expires_at=now + timedelta(minutes=30),
                )
            )
        try:
            yield
        finally:
            with self.engine.begin() as connection:
                connection.execute(delete(ResourceLease).where(ResourceLease.lease_id == lease_id))

    def storage(self, user_id: UUID, *, new_dataset: bool = False) -> None:
        with self.engine.connect() as connection:
            count, size = storage_usage(connection, user_id)
        if new_dataset and count >= self.settings.beta_max_datasets:
            raise HTTPException(429, "Đã đạt giới hạn workspace beta.")
        if size + self.settings.upload_max_bytes > self.settings.beta_max_user_bytes:
            raise HTTPException(429, "Đã đạt giới hạn dung lượng dữ liệu beta.")


def resource_control() -> ResourceControl:
    return ResourceControl(get_setup_engine(), get_settings())


def allow_provider_data() -> None:
    if not get_settings().beta_provider_data_enabled:
        raise HTTPException(403, "Quản trị viên chưa cho phép gửi dữ liệu tới AI providers.")
