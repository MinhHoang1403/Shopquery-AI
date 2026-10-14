"""FastAPI application entry point."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(router)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Prevent stack traces and internal exception details from reaching clients."""

    logging.getLogger(__name__).exception(
        "Unexpected API error on %s", request.url.path, exc_info=exc
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
