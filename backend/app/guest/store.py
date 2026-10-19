"""RAM-only page contexts; no guest files, vectors, or messages in user tables."""

import hashlib
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.datasets.parser import ParsedTable
from app.rag.chunking import DocumentChunkData


@dataclass(frozen=True)
class GuestFile:
    file_id: str
    filename: str
    size: int
    memory_bytes: int
    table: ParsedTable | None = None
    chunks: tuple[DocumentChunkData, ...] = ()


@dataclass
class GuestContext:
    key: str
    expires: float
    remaining: int
    files: list[GuestFile] = field(default_factory=list)
    uploaded_count: int = 0
    cancelled: threading.Event = field(default_factory=threading.Event)
    busy: threading.Lock = field(default_factory=threading.Lock)


class GuestStore:
    def __init__(self, settings: Settings, clock=time.monotonic) -> None:
        self.settings, self.clock = settings, clock
        self._contexts: dict[str, GuestContext] = {}
        self._lock = threading.RLock()

    def create(self) -> tuple[str, GuestContext]:
        with self._lock:
            self.cleanup()
            if len(self._contexts) >= self.settings.guest_max_sessions:
                raise HTTPException(429, "Hiện có quá nhiều phiên khách. Vui lòng thử lại sau.")
            raw = secrets.token_urlsafe(32)
            key = hashlib.sha256(raw.encode()).hexdigest()
            context = GuestContext(
                key,
                self.clock() + self.settings.guest_session_seconds,
                self.settings.guest_questions_per_session,
            )
            self._contexts[key] = context
            return raw, context

    def get(self, raw: str) -> GuestContext:
        if not raw or len(raw) > 128:
            raise HTTPException(401, "Thiếu phiên khách hợp lệ.")
        key = hashlib.sha256(raw.encode()).hexdigest()
        with self._lock:
            context = self._contexts.get(key)
            if context is None or context.cancelled.is_set() or context.expires <= self.clock():
                if context is not None:
                    self._release(key)
                raise HTTPException(
                    410, "Phiên khách đã hết hạn. Tải lại trang để bắt đầu phiên mới."
                )
            return context

    @contextmanager
    def operation(self, context: GuestContext):
        if not context.busy.acquire(blocking=False):
            raise HTTPException(429, "Phiên khách đang xử lý một yêu cầu khác.")
        try:
            self.ensure_active(context)
            yield
        finally:
            context.busy.release()

    def ensure_active(self, context: GuestContext) -> None:
        with self._lock:
            if (
                self._contexts.get(context.key) is not context
                or context.cancelled.is_set()
                or context.expires <= self.clock()
            ):
                raise HTTPException(410, "Phiên khách đã hết hạn. Tải lại trang để bắt đầu lại.")

    def consume_question(self, context: GuestContext) -> None:
        with self._lock:
            self.ensure_active(context)
            if context.remaining <= 0:
                raise HTTPException(
                    429,
                    "Bạn đã sử dụng hết lượt dùng thử. Đăng nhập để tiếp tục và lưu lịch sử.",
                    headers={"X-Guest-Limit": "chat"},
                )
            context.remaining -= 1

    def add_file(self, context: GuestContext, file: GuestFile) -> None:
        with self._lock:
            self.ensure_active(context)
            if context.uploaded_count >= self.settings.guest_max_files:
                raise HTTPException(429, "Đã đạt giới hạn số tệp của phiên khách.")
            size = sum(item.memory_bytes for item in context.files) + file.memory_bytes
            total = sum(item.memory_bytes for c in self._contexts.values() for item in c.files)
            chunks = sum(len(item.chunks) for item in context.files) + len(file.chunks)
            if (
                size > self.settings.guest_max_session_bytes
                or total + file.memory_bytes > self.settings.guest_max_total_bytes
                or chunks > self.settings.guest_max_chunks
            ):
                raise HTTPException(
                    429, "Dữ liệu tạm vượt giới hạn tài nguyên của phiên hoặc hệ thống."
                )
            context.files.append(file)
            context.uploaded_count += 1

    def reset(self, context: GuestContext) -> None:
        with self._lock:
            self._release(context.key)

    def _release(self, key: str) -> None:
        context = self._contexts.pop(key, None)
        if context:
            context.cancelled.set()
            context.files.clear()

    def cleanup(self) -> None:
        with self._lock:
            for key, context in list(self._contexts.items()):
                if context.expires <= self.clock():
                    self._release(key)

    def close(self) -> None:
        with self._lock:
            for key in list(self._contexts):
                self._release(key)


def file_metadata(file: GuestFile) -> dict[str, Any]:
    return {
        "file_id": file.file_id,
        "filename": file.filename,
        "size": file.size,
        "kind": "table" if file.table else "document",
        "row_count": file.table.row_count if file.table else None,
        "columns": [col.as_dict() for col in file.table.columns] if file.table else [],
        "chunk_count": len(file.chunks),
    }


@lru_cache
def guest_store() -> GuestStore:
    return GuestStore(get_settings())
