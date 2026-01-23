from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
import jwt


# bcrypt_sha256 снимает лимит 72 байта bcrypt и безопасно для длинных паролей.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)


COOKIE_NAME = "obsfog_token"


def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    return pwd_context.verify(pw, hashed)


def create_token(user_id: int, secret: str | None = None, minutes: int = 60 * 24 * 30) -> str:
    from .settings import Settings

    settings = Settings.load()
    secret = secret or settings.jwt_secret
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=minutes)).timestamp())}
    return jwt.encode(payload, secret, algorithm="HS256")


def get_current_user_id(request) -> int:
    from .settings import Settings

    settings = Settings.load()
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise ValueError("no token")
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return int(payload["sub"])


def new_stream_key() -> str:
    return secrets.token_urlsafe(16)[:32]
