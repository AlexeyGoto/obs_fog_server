from __future__ import annotations
import hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Request, HTTPException
from passlib.context import CryptContext
from .settings import Settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = Settings.load()

COOKIE_NAME = "obs_session"

def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)

def verify_password(pw: str, hashed: str) -> bool:
    return pwd_context.verify(pw, hashed)

def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": int(now.timestamp()), "exp": int((now + timedelta(days=30)).timestamp())}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def read_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

def get_current_user_id(request: Request) -> int:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return read_token(token)

def new_stream_key() -> str:
    return secrets.token_hex(16)
