from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # SQLite file path (used when Postgres is not configured)
    database_path: str
    # Optional Postgres DSN (postgresql://user:pass@host:port/db)
    database_url: str
    # Effective DB reference (either sqlite file path or postgres DSN)
    db_ref: str
    # Backend name: 'sqlite' or 'postgres'
    db_backend: str
    data_dir: str
    public_base_url: str
    default_save_videos: bool
    default_auto_delete: bool
    default_strict_keys: bool


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    val = val.strip().lower()
    if val in {"1", "true", "yes", "y", "on"}:
        return True
    if val in {"0", "false", "no", "n", "off"}:
        return False
    return default


def load_settings() -> Settings:
    sqlite_path = os.getenv("DATABASE_PATH", "/data/db/app.db")

    # Prefer DATABASE_URL, else allow POSTGRESQL_* split variables (удобнее для .env)
    # Для split-варианта используем key=value DSN, чтобы не упираться в URL-encoding пароля.
    db_url = (os.getenv("DATABASE_URL") or "").strip()

    pg_host = (os.getenv("POSTGRESQL_HOST") or "").strip()
    pg_port = (os.getenv("POSTGRESQL_PORT") or "5432").strip()
    pg_user = (os.getenv("POSTGRESQL_USER") or "").strip()
    pg_pass = (os.getenv("POSTGRESQL_PASSWORD") or "").strip()
    pg_db = (os.getenv("POSTGRESQL_DBNAME") or "").strip()

    if db_url:
        db_backend = "postgres"
        db_ref = db_url
    elif pg_host and pg_user and pg_db:
        db_backend = "postgres"
        # psycopg2 DSN
        db_ref = f"host={pg_host} port={pg_port} dbname={pg_db} user={pg_user} password={pg_pass}"
    else:
        db_backend = "sqlite"
        db_ref = sqlite_path

    return Settings(
        database_path=sqlite_path,
        database_url=db_url,
        db_ref=db_ref,
        db_backend=db_backend,
        data_dir=os.getenv("DATA_DIR", "/data"),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8080"),
        default_save_videos=_env_bool("DEFAULT_SAVE_VIDEOS", True),
        default_auto_delete=_env_bool("DEFAULT_AUTO_DELETE", True),
        default_strict_keys=_env_bool("DEFAULT_STRICT_KEYS", True),
    )
