from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v


def _bool(name: str, default: bool = False) -> bool:
    v = _get(name, None)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    app_base_url: str
    jwt_secret: str
    telegram_bot_token: str
    telegram_admin_id: int | None
    database_url: str
    hls_base_url: str
    max_telegram_bytes: int
    clip_seconds: int
    auto_delete: bool
    approval_required: bool

    @staticmethod
    def load() -> "Settings":
        app_base_url = (_get("APP_BASE_URL", "http://127.0.0.1:8080")).rstrip("/")
        jwt_secret = _get("JWT_SECRET", "change_me") or "change_me"
        telegram_bot_token = _get("TELEGRAM_BOT_TOKEN", "") or ""
        admin_id = _get("TELEGRAM_ADMIN_ID", "")
        telegram_admin_id = int(admin_id) if admin_id else None
        hls_base_url = (_get("HLS_BASE_URL", "http://nginx:8080/hls")).rstrip("/")
        database_url = _get("DATABASE_URL", "sqlite:////data/db/obs.db") or "sqlite:////data/db/obs.db"

        max_mb = int(_get("TELEGRAM_MAX_MB", "50") or "50")
        max_telegram_bytes = max_mb * 1024 * 1024

        clip_seconds = int(_get("CLIP_SECONDS", "420") or "420")
        auto_delete = (_get("AUTO_DELETE", "1") or "1") == "1"

        approval_required = _bool("APPROVAL_REQUIRED", False)

        return Settings(
            app_base_url=app_base_url,
            jwt_secret=jwt_secret,
            telegram_bot_token=telegram_bot_token,
            telegram_admin_id=telegram_admin_id,
            database_url=database_url,
            hls_base_url=hls_base_url,
            max_telegram_bytes=max_telegram_bytes,
            clip_seconds=clip_seconds,
            auto_delete=auto_delete,
            approval_required=approval_required,
        )
