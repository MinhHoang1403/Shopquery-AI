"""Authenticate private requests before repositories, parsers and AI work."""

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.auth.repository import AuthRepository, Principal
from app.core.config import get_settings
from app.core.diagnostics import diagnostic_stage
from app.database.session import get_setup_engine


def auth_repository() -> AuthRepository:
    return AuthRepository(get_setup_engine())


@diagnostic_stage("authentication", annotate_error=False)
def require_session(request: Request) -> Principal:
    settings = get_settings()
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        raise HTTPException(401, "Vui lòng đăng nhập.")
    principal = auth_repository().authenticate(raw)
    if principal.email.casefold() not in settings.auth_invited_emails:
        raise HTTPException(
            403, "Tài khoản không được mời truy cập beta.", headers={"X-Session-Invalid": "1"}
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        request.headers.get("origin") != settings.app_origin
        or not hmac.compare_digest(request.headers.get("x-csrf-token", ""), principal.csrf)
    ):
        raise HTTPException(403, "CSRF validation failed.")
    return principal


CurrentUser = Annotated[Principal, Depends(require_session)]
