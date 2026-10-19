"""Google login endpoints; application cookies contain only opaque secrets."""

import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.auth.dependencies import CurrentUser, auth_repository
from app.auth.limits import resource_control
from app.auth.oidc import google_client, verified_identity
from app.core.config import get_settings

router = APIRouter(prefix="/api/auth")


def flow_cookie() -> str:
    return "__Host-shopquery_oidc" if get_settings().secure_cookies else "shopquery_oidc"


def set_cookie(response: Response, name: str, value: str, seconds: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=seconds,
        httponly=True,
        secure=get_settings().secure_cookies,
        samesite="lax",
        path="/",
    )


@router.get("/login")
async def login(request: Request) -> Response:
    settings = get_settings()
    if request.query_params:
        raise HTTPException(400, "Login redirect không được phép.")
    client = google_client(settings)
    resource_control().login(request.client.host if request.client else "unknown")
    raw, state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    result = await client.create_authorization_url(
        redirect_uri=settings.oidc_callback_url,
        state=state,
        nonce=nonce,
        code_verifier=verifier,
        prompt="select_account",
    )
    auth_repository().save_flow(raw, state, nonce, verifier)
    response = RedirectResponse(result["url"], status_code=302)
    response.headers["Cache-Control"] = "no-store"
    set_cookie(response, flow_cookie(), raw, 600)
    return response


@router.get("/callback")
async def callback(request: Request) -> Response:
    settings = get_settings()
    raw = request.cookies.get(flow_cookie(), "")
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    if not raw or not state or not code or request.query_params.get("error"):
        raise HTTPException(400, "Google Sign-In không hoàn tất.")
    repository = auth_repository()
    resource_control().login(request.client.host if request.client else "unknown")
    nonce, verifier = repository.consume_flow(raw, state)
    try:
        identity = await verified_identity(google_client(settings), code, nonce, verifier, settings)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "Không thể xác minh Google Sign-In.") from exc
    user_id = repository.identity(*identity)
    token = repository.create_session(
        user_id, settings.auth_session_hours, request.cookies.get(settings.session_cookie_name)
    )
    response = RedirectResponse(settings.app_origin + "/", status_code=303)
    response.headers["Cache-Control"] = "no-store"
    set_cookie(response, settings.session_cookie_name, token, settings.auth_session_hours * 3600)
    response.delete_cookie(
        flow_cookie(), path="/", secure=settings.secure_cookies, httponly=True, samesite="lax"
    )
    return response


@router.get("/me")
def current_user(user: CurrentUser, response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "user": {
            "user_id": str(user.user_id),
            "email": user.email,
            "display_name": user.display_name,
        },
        "csrf_token": user.csrf,
    }


@router.post("/logout", status_code=204)
def logout(user: CurrentUser) -> Response:
    settings = get_settings()
    auth_repository().revoke(user.session_hash)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )
    return response
