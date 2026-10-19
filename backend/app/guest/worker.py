"""Disposable processes bound parsing/AI duration; TEMP connections die with them."""

import logging
import multiprocessing
import os
import pickle
import time
from multiprocessing.connection import Connection
from pathlib import PurePosixPath
from threading import Event
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.core.config import Settings
from app.core.errors import ResourceNotFoundError, UploadValidationError
from app.datasets.parser import parse_tabular_file
from app.guest.store import GuestFile
from app.rag.chunking import chunk_document
from app.rag.upload_parser import parse_document_file


def parse_guest_file(
    filename: str, content: bytes, sheet: str | None, settings: Settings
) -> GuestFile:
    if PurePosixPath(filename.replace("\\", "/")).suffix.lower() in {".csv", ".xlsx"}:
        table = parse_tabular_file(
            filename,
            content,
            sheet_name=sheet,
            max_bytes=settings.guest_max_file_bytes,
            max_rows=settings.guest_max_rows,
            max_columns=settings.guest_max_columns,
        )
        size = max(len(content), len(pickle.dumps(table)) * 4)
        return GuestFile(uuid4().hex, table.filename, len(content), size, table=table)
    document = parse_document_file(filename, content, max_bytes=settings.guest_max_file_bytes)
    if len(document.document.content) > settings.guest_max_characters:
        raise UploadValidationError("Nội dung tài liệu vượt giới hạn phiên khách.")
    chunks = tuple(chunk_document(document.document))
    if not chunks or len(chunks) > settings.guest_max_chunks:
        raise UploadValidationError("Số đoạn tài liệu vượt giới hạn phiên khách.")
    size = max(len(content), len(pickle.dumps(chunks)) * 4)
    return GuestFile(uuid4().hex, document.document.source_file, len(content), size, chunks=chunks)


def _worker_main(connection: Connection, action: str, payload: tuple, settings: Settings) -> None:
    try:
        logging.disable(logging.CRITICAL)
        try:
            import resource
        except ImportError:
            resource = None
        if resource is not None:
            memory = settings.guest_worker_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            cpu = settings.guest_worker_cpu_seconds
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        if action in {"parse", "relationship"}:
            for key in tuple(os.environ):
                if (
                    key.startswith(("GOOGLE_", "INETCLOUD_"))
                    or (action == "parse" and key.startswith("DATABASE_"))
                    or key == "GEMINI_API_KEY"
                ):
                    os.environ.pop(key, None)
        if action == "parse":
            # Keep the existing PDF/parser limits, with stricter guest bounds in this child only.
            import app.rag.upload_parser as parser

            parser.MAX_PDF_PAGES = settings.guest_max_pages
            parser.MAX_EXTRACTED_CHARACTERS = settings.guest_max_characters
            parser.MAX_DOCX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
            import app.datasets.parser as tables

            tables.MAX_XLSX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
            result = parse_guest_file(*payload, settings)
        elif action == "chat":
            from app.guest.pipeline import run_guest_chat

            if len(payload) == 3:
                result = run_guest_chat(payload[0], payload[1], settings, relationships=payload[2])
            else:
                result = run_guest_chat(*payload, settings)
        elif action == "relationship":
            from app.datasets.relationships import verify_relationship
            from app.guest.pipeline import GuestSqlDatabase

            files, request = payload
            database = GuestSqlDatabase(settings, files)
            try:
                with database.engine.connect() as sql:
                    result = verify_relationship(sql, request, database.file_tables)
            finally:
                database.close()
        else:
            raise ValueError("Unsupported internal operation")
        connection.send((True, result))
    except UploadValidationError as exc:
        connection.send((False, (422, str(exc))))
    except ResourceNotFoundError as exc:
        connection.send((False, (404, str(exc))))
    except BaseException:
        connection.send(
            (False, (502, "Không thể hoàn tất xử lý dữ liệu tạm. Không tạo kết quả giả."))
        )
    finally:
        connection.close()


def run_isolated(
    action: str,
    payload: tuple,
    settings: Settings,
    cancelled: Event,
    *,
    target=_worker_main,
) -> Any:
    context = multiprocessing.get_context("spawn")
    if action in {"parse", "relationship"}:
        settings = settings.model_copy(
            update={
                "google_client_id": None,
                "google_client_secret": None,
                "gemini_api_key": None,
                "inetcloud_base_url": None,
                "database_setup_url": "" if action == "parse" else settings.database_setup_url,
                "database_readonly_url": ""
                if action == "parse"
                else settings.database_readonly_url,
                "auth_invited_emails": [],
            }
        )
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=target, args=(send, action, payload, settings), daemon=True)
    timeout = (
        settings.guest_parse_timeout_seconds
        if action in {"parse", "relationship"}
        else settings.guest_request_timeout_seconds
    )
    deadline = time.monotonic() + timeout
    try:
        process.start()
        send.close()
        while time.monotonic() < deadline:
            if cancelled.is_set():
                raise HTTPException(410, "Phiên khách đã được giải phóng.")
            if receive.poll(0.05):
                try:
                    ok, result = receive.recv()
                except EOFError as exc:
                    raise HTTPException(
                        502, "Tác vụ tạm đã dừng an toàn, không có kết quả."
                    ) from exc
                if not ok:
                    raise HTTPException(*result)
                return result
            if not process.is_alive():
                raise HTTPException(502, "Tác vụ tạm đã dừng an toàn, không có kết quả.")
        raise HTTPException(504, "Tác vụ khách vượt thời gian xử lý và đã được dừng.")
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            process.close()
        receive.close()
        send.close()
