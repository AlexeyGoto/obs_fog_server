from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .settings import settings

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

JWT_ALG = 'HS256'
COOKIE_NAME = 'obsfog_session'


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_token(user_id: int, expires_minutes: int = 60 * 24 * 30) -> str:
    now = datetime.utcnow()
    payload = {
        'sub': str(user_id),
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


def get_user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])
        user_id = int(payload.get('sub'))
    except (JWTError, ValueError, TypeError):
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail='Not authenticated')
    return user


