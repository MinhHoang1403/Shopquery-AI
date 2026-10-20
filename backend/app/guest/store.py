"""RAM-only page contexts; no guest files, vectors, or messages in user tables."""

import hashlib
import pickle
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
from app.datasets.relationships import MAX_RELATIONSHIPS, RelationshipRecord
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
    relationships: list[RelationshipRecord] = field(default_factory=list)
    uploaded_count: int = 0
    parse_count: int = 0
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

    def add_file(
        self,
        context: GuestContext,
        file: GuestFile,
        relationships: tuple[RelationshipRecord, ...] = (),
    ) -> None:
        with self._lock:
            self.ensure_active(context)
            if context.uploaded_count >= self.settings.guest_max_files:
                raise HTTPException(429, "Đã đạt giới hạn số tệp của phiên khách.")
            table_ids = {f.file_id for f in [*context.files, file] if f.table}
            if any(
                r.source_table_id not in table_ids
                or r.target_table_id not in table_ids
                or r.origin != "automatic"
                for r in relationships
            ):
                raise HTTPException(404, "Liên kết không thuộc các tệp của phiên này.")
            if len(context.relationships) + len(relationships) > MAX_RELATIONSHIPS:
                raise HTTPException(429, "Phiên đã đạt giới hạn liên kết.")
            added = file.memory_bytes + sum(len(pickle.dumps(r)) * 4 + 256 for r in relationships)
            size = self._memory_bytes(context) + added
            total = sum(self._memory_bytes(c) for c in self._contexts.values())
            chunks = sum(len(item.chunks) for item in context.files) + len(file.chunks)
            if (
                size > self.settings.guest_max_session_bytes
                or total + added > self.settings.guest_max_total_bytes
                or chunks > self.settings.guest_max_chunks
            ):
                raise HTTPException(
                    429, "Dữ liệu tạm vượt giới hạn tài nguyên của phiên hoặc hệ thống."
                )
            context.files.append(file)
            context.relationships.extend(relationships)
            context.uploaded_count += 1

    @staticmethod
    def _memory_bytes(context: GuestContext) -> int:
        return sum(item.memory_bytes for item in context.files) + (
            len(pickle.dumps(context.relationships)) * 4 if context.relationships else 0
        )

    def confirm_relationship(
        self,
        context: GuestContext,
        record: RelationshipRecord,
    ) -> RelationshipRecord:
        with self._lock:
            self.ensure_active(context)
            table_ids = {file.file_id for file in context.files if file.table is not None}
            if (
                record.source_table_id not in table_ids
                or record.target_table_id not in table_ids
                or record.source_table_id == record.target_table_id
            ):
                raise HTTPException(404, "Hai bảng phải thuộc phiên hiện tại.")
            existing = next(
                (
                    item
                    for item in context.relationships
                    if (
                        item.source_table_id,
                        item.source_column,
                        item.target_table_id,
                        item.target_column,
                    )
                    == (
                        record.source_table_id,
                        record.source_column,
                        record.target_table_id,
                        record.target_column,
                    )
                ),
                None,
            )
            if existing:
                if record.origin == "manual" and existing.origin == "automatic":
                    record = record.model_copy(update={"relationship_id": existing.relationship_id})
                    context.relationships[context.relationships.index(existing)] = record
                    return record
                return existing
            if len(context.relationships) >= MAX_RELATIONSHIPS:
                raise HTTPException(429, "Phiên đã đạt giới hạn 20 liên kết.")
            added = len(pickle.dumps(record)) * 4 + 256
            if (
                self._memory_bytes(context) + added > self.settings.guest_max_session_bytes
                or sum(self._memory_bytes(c) for c in self._contexts.values()) + added
                > self.settings.guest_max_total_bytes
            ):
                raise HTTPException(429, "Liên kết vượt giới hạn bộ nhớ phiên khách.")
            context.relationships.append(record)
            return record

    def delete_relationship(self, context: GuestContext, relationship_id: str) -> None:
        with self._lock:
            self.ensure_active(context)
            item = next(
                (r for r in context.relationships if r.relationship_id == relationship_id), None
            )
            if item is None:
                raise HTTPException(404, "Không tìm thấy liên kết trong phiên này.")
            context.relationships.remove(item)

    def reset(self, context: GuestContext) -> None:
        with self._lock:
            self._release(context.key)

    def _release(self, key: str) -> None:
        context = self._contexts.pop(key, None)
        if context:
            context.cancelled.set()
            context.files.clear()
            context.relationships.clear()

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
