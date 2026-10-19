"""IP budgets and concurrency leases contain hashes only, never guest content."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.auth.limits import ResourceControl
from app.core.config import Settings
from app.database.models import ResourceLimit


class GuestControl(ResourceControl):
    def ip_rate(self, ip: str, action: str, limit: int) -> None:
        try:
            self.rate("guest:" + action + ":" + hashlib.sha256(ip.encode()).hexdigest(), limit)
        except HTTPException as exc:
            if exc.status_code == 429:
                raise HTTPException(
                    429,
                    "Đã hết ngân sách dùng thử theo IP. Đăng nhập hoặc thử lại sau.",
                    headers={**(exc.headers or {}), "X-Guest-Limit": action},
                ) from exc
            raise

    @contextmanager
    def lease(self, key: str, settings: Settings) -> Iterator[None]:
        lease_key = "guest:lease:" + key
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(71948104)"))
            connection.execute(delete(ResourceLimit).where(ResourceLimit.expires_at < now))
            count = connection.scalar(
                select(func.count())
                .select_from(ResourceLimit)
                .where(ResourceLimit.key.startswith("guest:lease:"))
            )
            own = connection.scalar(select(ResourceLimit.key).where(ResourceLimit.key == lease_key))
            if own or count >= settings.guest_system_concurrency:
                raise HTTPException(429, "Phiên khách hoặc hệ thống đang bận. Vui lòng thử lại.")
            connection.execute(
                insert(ResourceLimit).values(
                    key=lease_key,
                    count=1,
                    expires_at=now + timedelta(seconds=settings.guest_request_timeout_seconds + 30),
                )
            )
        try:
            yield
        finally:
            with self.engine.begin() as connection:
                connection.execute(delete(ResourceLimit).where(ResourceLimit.key == lease_key))
