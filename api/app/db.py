from __future__ import annotations

import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple


def now_ts() -> int:
    return int(time.time())


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


@contextmanager
def db_conn(db_path: str):
    ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str, default_save_videos: bool, default_auto_delete: bool, default_strict_keys: bool) -> None:
    with db_conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                stream_key TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS streams (
                stream_key TEXT PRIMARY KEY,
                is_live INTEGER NOT NULL,
                last_publish_at INTEGER,
                last_unpublish_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stream_key TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                message TEXT,
                output_path TEXT
            )
            """
        )

        # defaults (only if missing)
        _setting_set_if_missing(conn, "save_videos", "true" if default_save_videos else "false")
        _setting_set_if_missing(conn, "auto_delete", "true" if default_auto_delete else "false")
        _setting_set_if_missing(conn, "strict_keys", "true" if default_strict_keys else "false")


def _setting_set_if_missing(conn: sqlite3.Connection, key: str, value: str) -> None:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO settings(key, value) VALUES(?, ?)", (key, value))


def setting_get(db_path: str, key: str, default: str) -> str:
    with db_conn(db_path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default


def setting_set(db_path: str, key: str, value: str) -> None:
    with db_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def settings_all(db_path: str) -> Dict[str, str]:
    with db_conn(db_path) as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def _normalize_name(name: str) -> str:
    name = (name or "").strip()
    return name[:200] if name else "ПК"


def generate_stream_key(prefix: str = "pc") -> str:
    # nginx will use $name as stream key; keep it safe
    rand = secrets.token_urlsafe(10)
    rand = "".join(ch for ch in rand if ch.isalnum())
    return f"{prefix}-{rand.lower()}"


def pc_create(db_path: str, name: str) -> Tuple[int, str, str]:
    name = _normalize_name(name)
    # prefix from name (latin/digits only)
    base = "".join(ch.lower() for ch in name if ch.isalnum())
    base = base[:12] or "pc"

    for _ in range(10):
        key = generate_stream_key(base)
        with db_conn(db_path) as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO pcs(name, stream_key, created_at) VALUES(?, ?, ?)",
                    (name, key, now_ts()),
                )
                pc_id = int(cur.lastrowid)
                return pc_id, name, key
            except sqlite3.IntegrityError:
                continue
    raise RuntimeError("Не удалось сгенерировать уникальный stream_key")


def pc_list(db_path: str) -> List[Dict[str, Any]]:
    with db_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.name, p.stream_key, p.created_at,
                   COALESCE(s.is_live, 0) AS is_live,
                   s.last_publish_at, s.last_unpublish_at
            FROM pcs p
            LEFT JOIN streams s ON s.stream_key = p.stream_key
            ORDER BY p.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def pc_get(db_path: str, pc_id: int) -> Optional[Dict[str, Any]]:
    with db_conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT p.id, p.name, p.stream_key, p.created_at,
                   COALESCE(s.is_live, 0) AS is_live,
                   s.last_publish_at, s.last_unpublish_at
            FROM pcs p
            LEFT JOIN streams s ON s.stream_key = p.stream_key
            WHERE p.id=?
            """,
            (pc_id,),
        ).fetchone()
        return dict(row) if row else None


def pc_by_stream_key(db_path: str, stream_key: str) -> Optional[Dict[str, Any]]:
    with db_conn(db_path) as conn:
        row = conn.execute("SELECT id, name, stream_key, created_at FROM pcs WHERE stream_key=?", (stream_key,)).fetchone()
        return dict(row) if row else None


def stream_set_live(db_path: str, stream_key: str, is_live: bool) -> None:
    ts = now_ts()
    with db_conn(db_path) as conn:
        existing = conn.execute("SELECT stream_key FROM streams WHERE stream_key=?", (stream_key,)).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO streams(stream_key, is_live, last_publish_at, last_unpublish_at) VALUES(?, ?, ?, ?)",
                (stream_key, 1 if is_live else 0, ts if is_live else None, ts if not is_live else None),
            )
        else:
            if is_live:
                conn.execute(
                    "UPDATE streams SET is_live=1, last_publish_at=? WHERE stream_key=?",
                    (ts, stream_key),
                )
            else:
                conn.execute(
                    "UPDATE streams SET is_live=0, last_unpublish_at=? WHERE stream_key=?",
                    (ts, stream_key),
                )


def live_streams(db_path: str) -> List[str]:
    with db_conn(db_path) as conn:
        rows = conn.execute("SELECT stream_key FROM streams WHERE is_live=1 ORDER BY last_publish_at DESC").fetchall()
        return [r["stream_key"] for r in rows]


def job_create(db_path: str, stream_key: str, message: str = "") -> int:
    ts = now_ts()
    with db_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO jobs(stream_key, status, created_at, updated_at, message) VALUES(?, 'queued', ?, ?, ?)",
            (stream_key, ts, ts, message),
        )
        return int(cur.lastrowid)


def job_claim_next(db_path: str) -> Optional[Dict[str, Any]]:
    with db_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        job_id = int(row["id"])
        conn.execute("UPDATE jobs SET status='running', updated_at=? WHERE id=?", (now_ts(), job_id))
        row2 = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row2) if row2 else None


def job_update(db_path: str, job_id: int, status: str, message: str = "", output_path: Optional[str] = None) -> None:
    with db_conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status=?, updated_at=?, message=?, output_path=? WHERE id=?",
            (status, now_ts(), message, output_path, job_id),
        )


def jobs_recent(db_path: str, limit: int = 50) -> List[Dict[str, Any]]:
    with db_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]
