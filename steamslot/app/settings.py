from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


def _get_env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v


def _bool_env(name: str, default: bool = False) -> bool:
    v = _get_env(name, None)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    v = _get_env(name, None)
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _build_db_url_from_parts(prefix: str = "POSTGRESQL_") -> str | None:
    host = _get_env(prefix + "HOST", None)
    if not host:
        return None

    port = _get_env(prefix + "PORT", "5432") or "5432"
    user = _get_env(prefix + "USER", None)
    password = _get_env(prefix + "PASSWORD", None)
    dbname = _get_env(prefix + "DBNAME", None)

    if not user or not password or not dbname:
        return None

    sslmode = _get_env(prefix + "SSLMODE", None)  # disable / require / verify-full
    sslrootcert = _get_env(prefix + "SSLROOTCERT", None)

    user_q = quote_plus(user)
    pass_q = quote_plus(password)

    base = f"postgresql+psycopg://{user_q}:{pass_q}@{host}:{port}/{dbname}"

    params: list[str] = []
    if sslmode:
        params.append(f"sslmode={quote_plus(sslmode)}")
    if sslrootcert:
        params.append(f"sslrootcert={quote_plus(sslrootcert)}")

    if params:
        return base + "?" + "&".join(params)
    return base


@dataclass(frozen=True)
class Settings:
    root_path: str
    database_url: str

    admin_user: str
    admin_pass: str

    # cookie-session для админки
    session_key: str | None
    session_ttl_seconds: int
    cookie_secure: bool
    cookie_name: str

    # API keys
    master_api_key: str | None
    file_enc_key: str | None

    # Leases
    default_lease_ttl_seconds: int
    max_lease_ttl_seconds: int

    # PC auth
    require_pc_key: bool

    @staticmethod
    def load() -> "Settings":
        # Автоподхват .env из корня проекта (для локального запуска). Не перетирает уже заданные переменные окружения.
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=str(env_path), override=False)

        root_path = _get_env("STEAMSLOT_ROOT_PATH", "/steamslot") or "/steamslot"

        # ВАЖНО: SteamSlot должен жить в своей БД, т.к. у OBS тоже есть таблица pcs.
        database_url = _get_env("STEAMSLOT_DATABASE_URL", None)
        if not database_url:
            database_url = _get_env("DATABASE_URL", None)  # fallback
        if not database_url:
            database_url = _build_db_url_from_parts(prefix="STEAMSLOT_POSTGRESQL_")
        if not database_url:
            database_url = _build_db_url_from_parts(prefix="POSTGRESQL_")
        if not database_url:
            database_url = "sqlite:////data/db/steamslot.db"

        # Явные переменные для SteamSlot, но оставляем fallback на общий ADMIN_USER/ADMIN_PASS
        admin_user = _get_env("STEAMSLOT_ADMIN_USER", None) or (_get_env("ADMIN_USER", "admin") or "admin")
        admin_pass = _get_env("STEAMSLOT_ADMIN_PASS", None) or (_get_env("ADMIN_PASS", "changeme") or "changeme")

        session_key = _get_env("STEAMSLOT_SESSION_KEY", None)
        session_ttl_seconds = _int_env("STEAMSLOT_SESSION_TTL_SECONDS", 12 * 60 * 60)  # 12h
        cookie_secure = _bool_env("STEAMSLOT_COOKIE_SECURE", False)
        cookie_name = _get_env("STEAMSLOT_COOKIE_NAME", "steamslot_session") or "steamslot_session"

        master_api_key = _get_env("MASTER_API_KEY", None)
        file_enc_key = _get_env("FILE_ENC_KEY", None)

        default_ttl = _int_env("DEFAULT_LEASE_TTL_SECONDS", 600)
        max_ttl = _int_env("MAX_LEASE_TTL_SECONDS", 1800)

        require_pc_key = (_get_env("REQUIRE_PC_KEY", "1") or "1") == "1"

        return Settings(
            root_path=root_path,
            database_url=database_url,
            admin_user=admin_user,
            admin_pass=admin_pass,
            session_key=session_key,
            session_ttl_seconds=session_ttl_seconds,
            cookie_secure=cookie_secure,
            cookie_name=cookie_name,
            master_api_key=master_api_key,
            file_enc_key=file_enc_key,
            default_lease_ttl_seconds=default_ttl,
            max_lease_ttl_seconds=max_ttl,
            require_pc_key=require_pc_key,
        )
