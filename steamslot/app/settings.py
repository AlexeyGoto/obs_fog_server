from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from urllib.parse import quote_plus


def _get_env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v


def _build_db_url_from_parts() -> str | None:
    host = _get_env("POSTGRESQL_HOST", None)
    if not host:
        return None

    port = _get_env("POSTGRESQL_PORT", "5432") or "5432"
    user = _get_env("POSTGRESQL_USER", None)
    password = _get_env("POSTGRESQL_PASSWORD", None)
    dbname = _get_env("POSTGRESQL_DBNAME", None)

    if not user or not password or not dbname:
        return None

    sslmode = _get_env("POSTGRESQL_SSLMODE", None)  # disable / require / verify-full
    sslrootcert = _get_env("POSTGRESQL_SSLROOTCERT", None)

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
    master_api_key: str | None
    file_enc_key: str | None

    default_lease_ttl_seconds: int
    max_lease_ttl_seconds: int

    require_pc_key: bool

    @staticmethod
    def load() -> "Settings":

        # Автоподхват .env из корня проекта (для локального запуска)
        # Не перетирает уже заданные переменные окружения.
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=str(env_path), override=False)
        database_url = _get_env("DATABASE_URL", None)
        if not database_url:
            database_url = _build_db_url_from_parts()
        if not database_url:
            database_url = "sqlite+pysqlite:///./dev.db"

        admin_user = _get_env("ADMIN_USER", "admin") or "admin"
        admin_pass = _get_env("ADMIN_PASS", "changeme") or "changeme"
        master_api_key = _get_env("MASTER_API_KEY", None)
        file_enc_key = _get_env("FILE_ENC_KEY", None)

        default_ttl = int(_get_env("DEFAULT_LEASE_TTL_SECONDS", "600") or "600")
        max_ttl = int(_get_env("MAX_LEASE_TTL_SECONDS", "1800") or "1800")

        require_pc_key = (_get_env("REQUIRE_PC_KEY", "1") or "1") == "1"

        root_path = _get_env("STEAMSLOT_ROOT_PATH", "/steamslot") or "/steamslot"

        return Settings(
            database_url=database_url,
            admin_user=admin_user,
            admin_pass=admin_pass,
            master_api_key=master_api_key,
            file_enc_key=file_enc_key,
            default_lease_ttl_seconds=default_ttl,
            max_lease_ttl_seconds=max_ttl,
            require_pc_key=require_pc_key,
            root_path=root_path,
        )
