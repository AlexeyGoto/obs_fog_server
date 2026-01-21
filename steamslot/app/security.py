from __future__ import annotations

import secrets
from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from cryptography.fernet import Fernet, InvalidToken

basic = HTTPBasic()


@dataclass(frozen=True)
class FernetBox:
    fernet: Fernet

    @staticmethod
    def from_env_key(key: str | None) -> "FernetBox | None":
        if not key:
            return None
        Fernet(key.encode("utf-8"))
        return FernetBox(fernet=Fernet(key.encode("utf-8")))

    def encrypt(self, data: bytes) -> bytes:
        return self.fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        try:
            return self.fernet.decrypt(data)
        except InvalidToken as e:
            raise ValueError("Cannot decrypt data: wrong FILE_ENC_KEY?") from e


def admin_auth(settings):
    def _dep(creds: HTTPBasicCredentials = Depends(basic)):
        ok_user = secrets.compare_digest(creds.username, settings.admin_user)
        ok_pass = secrets.compare_digest(creds.password, settings.admin_pass)
        if not (ok_user and ok_pass):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Basic"},
            )
        return creds.username

    return _dep
