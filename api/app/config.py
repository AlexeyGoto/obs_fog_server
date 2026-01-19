from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str
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
    return Settings(
        database_path=os.getenv("DATABASE_PATH", "/data/db/app.db"),
        data_dir=os.getenv("DATA_DIR", "/data"),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8080"),
        default_save_videos=_env_bool("DEFAULT_SAVE_VIDEOS", True),
        default_auto_delete=_env_bool("DEFAULT_AUTO_DELETE", True),
        default_strict_keys=_env_bool("DEFAULT_STRICT_KEYS", True),
    )
