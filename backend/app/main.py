"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.relationship_routes import router as relationship_router
from app.api.routes import router
from app.auth.routes import router as auth_router
from app.core import observability
from app.core.config import get_settings
from app.core.diagnostics import STAGES, diagnostic_request, record_facts
from app.core.logging import configure_logging
from app.guest.middleware import GuestBodyLimit
from app.guest.relationship_routes import router as guest_relationship_router
from app.guest.routes import router as guest_router
from app.guest.store import guest_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    observability.configure(get_settings(), STAGES)

    async def cleanup_guests():
        while True:
            await asyncio.sleep(get_settings().guest_cleanup_seconds)
            guest_store().cleanup()

    task = asyncio.create_task(cleanup_guests())
    try:
        yield
    finally:
        guest_store().close()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await asyncio.to_thread(observability.shutdown)


settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Guest-Token", "X-Guest-CSRF"],
)
app.add_middleware(GuestBodyLimit)
app.include_router(router)
app.include_router(relationship_router)
app.include_router(auth_router)
app.include_router(guest_router)
app.include_router(guest_relationship_router)


@app.middleware("http")
async def private_no_store(request: Request, call_next):
    try:
        response = await call_next(request)
    finally:
        if request.url.path == "/api/auth/callback":
            request.scope["query_string"] = b""
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Prevent stack traces and internal exception details from reaching clients."""

    logging.getLogger(__name__).error(
        "Unexpected API error on %s (%s)", request.url.path, type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content={
            "answer": "Hệ thống gặp lỗi nội bộ.",
            "route": None,
            "sql": None,
            "rows": [],
            "sources": [],
            "error": "internal_error",
        },
    )


@app.middleware("http")
async def request_diagnostics(request: Request, call_next):
    if (
        request.method != "POST"
        or not request.url.path.startswith("/api/")
        or request.url.path.startswith("/api/auth/")
    ):
        return await call_next(request)
    with diagnostic_request() as trace:
        response = await call_next(request)
        if response.status_code >= 400:
            record_facts(final_status="failure")
        response.headers["X-Request-ID"] = trace.correlation_id
        return response
