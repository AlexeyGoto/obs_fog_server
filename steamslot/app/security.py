from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials


basic = HTTPBasic(auto_error=False)


@dataclass(frozen=True)
class FernetBox:
    """Шифрование файлов аккаунтов (SteamGuard и т.п.)."""
    fernet: Fernet

    @staticmethod
    def from_env_key(key: str | None) -> "FernetBox | None":
        if not key:
            return None
        Fernet(key.encode("utf-8"))  # validate
        return FernetBox(fernet=Fernet(key.encode("utf-8")))

    def encrypt(self, data: bytes) -> bytes:
        return self.fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        try:
            return self.fernet.decrypt(data)
        except InvalidToken as e:
            raise ValueError("Cannot decrypt data: wrong FILE_ENC_KEY?") from e


class AdminSession:
    """Cookie-session для админки SteamSlot."""

    def __init__(self, fernet: Fernet, ttl_seconds: int):
        self._fernet = fernet
        self._ttl = int(ttl_seconds)

    @staticmethod
    def from_env_key(key: str | None, ttl_seconds: int) -> "AdminSession":
        if not key:
            # Эфемерный ключ (сессии сбросятся при рестарте). Для продакшна задайте STEAMSLOT_SESSION_KEY.
            key = Fernet.generate_key().decode("utf-8")
            print("[WARN] STEAMSLOT_SESSION_KEY is not set. Generated ephemeral key; admin sessions will reset on restart.")
        f = Fernet(key.encode("utf-8"))
        return AdminSession(fernet=f, ttl_seconds=ttl_seconds)

    def issue(self, username: str) -> str:
        payload = {"u": username}
        token = self._fernet.encrypt(json.dumps(payload).encode("utf-8"))
        return token.decode("utf-8")

    def verify(self, token: str) -> Optional[str]:
        if not token:
            return None
        try:
            raw = self._fernet.decrypt(token.encode("utf-8"), ttl=self._ttl)
            payload = json.loads(raw.decode("utf-8"))
            u = payload.get("u")
            if isinstance(u, str) and u:
                return u
            return None
        except InvalidToken:
            return None
        except Exception:
            return None


def basic_auth_user(settings, creds: HTTPBasicCredentials | None) -> str | None:
    if creds is None:
        return None
    ok_user = secrets.compare_digest(creds.username, settings.admin_user)
    ok_pass = secrets.compare_digest(creds.password, settings.admin_pass)
    if ok_user and ok_pass:
        return creds.username
    return None


def get_admin_user(request: Request, settings, session_mgr: AdminSession) -> str | None:
    # 1) cookie session
    token = request.cookies.get(settings.cookie_name, "")
    u = session_mgr.verify(token)
    if u:
        return u

    # 2) fallback basic auth (для совместимости)
    creds = request.state._basic_creds if hasattr(request.state, "_basic_creds") else None
    if creds:
        return basic_auth_user(settings, creds)

    return None


def require_admin(settings, session_mgr: AdminSession):
    def _dep(request: Request, creds: HTTPBasicCredentials | None = Depends(basic)):
        # сохраняем creds для get_admin_user (если middleware вызовет позже)
        request.state._basic_creds = creds
        u = get_admin_user(request, settings, session_mgr)
        if not u:
            # Для API-401 оставляем WWW-Authenticate. Для веб-редиректа используем middleware.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Basic"},
            )
        return u

    return _dep
