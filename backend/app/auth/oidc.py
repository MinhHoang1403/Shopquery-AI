"""Google protocol and signature validation delegated to Authlib."""

from authlib.integrations.starlette_client import OAuth
from authlib.integrations.starlette_client.apps import StarletteOAuth2App
from fastapi import HTTPException

from app.auth.repository import GOOGLE_ISSUER
from app.core.config import Settings


def google_client(settings: Settings) -> StarletteOAuth2App:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(503, "Chưa cấu hình Google Sign-In.")
    oauth = OAuth()
    return oauth.register(
        "google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=f"{GOOGLE_ISSUER}/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",
            "timeout": 15,
        },
    )


async def verified_identity(
    client: StarletteOAuth2App, code: str, nonce: str, verifier: str, settings: Settings
) -> tuple[str, str, str]:
    token = await client.fetch_access_token(
        code=code,
        redirect_uri=settings.oidc_callback_url,
        code_verifier=verifier,
    )
    claims = await client.parse_id_token(
        token,
        nonce=nonce,
        leeway=30,
        claims_options={
            "iss": {"essential": True, "values": [GOOGLE_ISSUER]},
            "aud": {"essential": True, "value": settings.google_client_id},
            "exp": {"essential": True},
            "sub": {"essential": True},
        },
    )
    if not claims or claims.get("email_verified") is not True:
        raise HTTPException(403, "Google email chưa được xác minh.")
    email = str(claims.get("email", "")).casefold()
    if email not in settings.auth_invited_emails:
        raise HTTPException(403, "Tài khoản không được mời truy cập beta.")
    return str(claims["sub"]), email, str(claims.get("name") or email)
