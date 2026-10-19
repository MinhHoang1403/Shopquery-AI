"""Server-side identities, hashed sessions and one-use browser-bound OIDC flows."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import OidcFlow, User, UserSession

GOOGLE_ISSUER = "https://accounts.google.com"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"shopquery-csrf-v1", hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    email: str
    display_name: str
    session_hash: str
    csrf: str


class AuthRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def identity(self, subject: str, email: str, display_name: str) -> UUID:
        with self.engine.begin() as connection:
            statement = insert(User).values(
                issuer=GOOGLE_ISSUER,
                subject=subject,
                email=email,
                display_name=display_name[:200],
                active=True,
            )
            user_id = connection.scalar(
                statement.on_conflict_do_update(
                    constraint="uq_users_identity",
                    set_={
                        "email": email,
                        "display_name": display_name[:200],
                        "updated_at": datetime.now(UTC),
                    },
                ).returning(User.user_id)
            )
        return user_id

    def create_session(self, user_id: UUID, hours: int, old_token: str | None = None) -> str:
        raw = secrets.token_urlsafe(32)
        with self.engine.begin() as connection:
            active = connection.scalar(select(User.active).where(User.user_id == user_id))
            if active is not True:
                raise HTTPException(403, "Tài khoản không được phép truy cập.")
            if old_token:
                connection.execute(
                    update(UserSession)
                    .where(UserSession.token_hash == token_hash(old_token))
                    .values(revoked_at=datetime.now(UTC))
                )
            connection.execute(
                insert(UserSession).values(
                    token_hash=token_hash(raw),
                    user_id=user_id,
                    expires_at=datetime.now(UTC) + timedelta(hours=hours),
                )
            )
        return raw

    def authenticate(self, raw: str) -> Principal:
        if not 32 <= len(raw) <= 100:
            raise HTTPException(401, "Phiên đăng nhập không hợp lệ.")
        with Session(self.engine) as session:
            user = session.scalar(
                select(User)
                .join(UserSession)
                .where(
                    UserSession.token_hash == token_hash(raw),
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > datetime.now(UTC),
                    User.active.is_(True),
                )
            )
            if user is None:
                raise HTTPException(401, "Phiên đăng nhập đã hết hạn hoặc không hợp lệ.")
            return Principal(
                user.user_id, user.email, user.display_name, token_hash(raw), csrf_token(raw)
            )

    def revoke(self, session_hash: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(UserSession)
                .where(UserSession.token_hash == session_hash)
                .values(revoked_at=datetime.now(UTC))
            )

    def save_flow(self, raw: str, state: str, nonce: str, verifier: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(delete(OidcFlow).where(OidcFlow.expires_at < datetime.now(UTC)))
            connection.execute(
                insert(OidcFlow).values(
                    token_hash=token_hash(raw),
                    state=state,
                    nonce=nonce,
                    code_verifier=verifier,
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )

    def consume_flow(self, raw: str, state: str) -> tuple[str, str]:
        with self.engine.begin() as connection:
            row = connection.execute(
                delete(OidcFlow)
                .where(
                    OidcFlow.token_hash == token_hash(raw),
                    OidcFlow.state == state,
                    OidcFlow.expires_at > datetime.now(UTC),
                )
                .returning(OidcFlow.nonce, OidcFlow.code_verifier)
            ).first()
        if row is None:
            raise HTTPException(400, "Yêu cầu đăng nhập không hợp lệ hoặc đã sử dụng.")
        return row.nonce, row.code_verifier
