from __future__ import annotations

import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # pragma: no cover
    psycopg2 = None  # type: ignore
    RealDictCursor = None  # type: ignore


def now_ts() -> int:
    return int(time.time())


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _is_postgres(db_ref: str) -> bool:
    ref = (db_ref or "").strip().lower()
    if not ref:
        return False
    if ref.startswith("postgres://") or ref.startswith("postgresql://"):
        return True
    # psycopg2 key=value DSN
    if "host=" in ref and "dbname=" in ref:
        return True
    return False


# ---------------- SQLite backend ----------------


@contextmanager
def _sqlite_conn(db_path: str):
    ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _sqlite_init_db(db_path: str, default_save_videos: bool, default_auto_delete: bool, default_strict_keys: bool) -> None:
    with _sqlite_conn(db_path) as conn:
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
        _sqlite_setting_set_if_missing(conn, "save_videos", "true" if default_save_videos else "false")
        _sqlite_setting_set_if_missing(conn, "auto_delete", "true" if default_auto_delete else "false")
        _sqlite_setting_set_if_missing(conn, "strict_keys", "true" if default_strict_keys else "false")


def _sqlite_setting_set_if_missing(conn: sqlite3.Connection, key: str, value: str) -> None:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO settings(key, value) VALUES(?, ?)", (key, value))


def _sqlite_setting_get(db_path: str, key: str, default: str) -> str:
    with _sqlite_conn(db_path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default


def _sqlite_setting_set(db_path: str, key: str, value: str) -> None:
    with _sqlite_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def _sqlite_settings_all(db_path: str) -> Dict[str, str]:
    with _sqlite_conn(db_path) as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def _normalize_name(name: str) -> str:
    name = (name or "").strip()
    return name[:200] if name else "ПК"


def generate_stream_key(prefix: str = "pc") -> str:
    rand = secrets.token_urlsafe(10)
    rand = "".join(ch for ch in rand if ch.isalnum())
    return f"{prefix}-{rand.lower()}"


def _sqlite_pc_create(db_path: str, name: str) -> Tuple[int, str, str]:
    name = _normalize_name(name)
    base = "".join(ch.lower() for ch in name if ch.isalnum())
    base = base[:12] or "pc"

    for _ in range(10):
        key = generate_stream_key(base)
        with _sqlite_conn(db_path) as conn:
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


def _sqlite_pc_list(db_path: str) -> List[Dict[str, Any]]:
    with _sqlite_conn(db_path) as conn:
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


def _sqlite_pc_get(db_path: str, pc_id: int) -> Optional[Dict[str, Any]]:
    with _sqlite_conn(db_path) as conn:
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


def _sqlite_pc_by_stream_key(db_path: str, stream_key: str) -> Optional[Dict[str, Any]]:
    with _sqlite_conn(db_path) as conn:
        row = conn.execute("SELECT id, name, stream_key, created_at FROM pcs WHERE stream_key=?", (stream_key,)).fetchone()
        return dict(row) if row else None


def _sqlite_stream_set_live(db_path: str, stream_key: str, is_live: bool) -> None:
    ts = now_ts()
    with _sqlite_conn(db_path) as conn:
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


def _sqlite_live_streams(db_path: str) -> List[str]:
    with _sqlite_conn(db_path) as conn:
        rows = conn.execute("SELECT stream_key FROM streams WHERE is_live=1 ORDER BY last_publish_at DESC").fetchall()
        return [r["stream_key"] for r in rows]


def _sqlite_job_create(db_path: str, stream_key: str, message: str = "") -> int:
    ts = now_ts()
    with _sqlite_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO jobs(stream_key, status, created_at, updated_at, message) VALUES(?, 'queued', ?, ?, ?)",
            (stream_key, ts, ts, message),
        )
        return int(cur.lastrowid)


def _sqlite_job_claim_next(db_path: str) -> Optional[Dict[str, Any]]:
    with _sqlite_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY id ASC LIMIT 1").fetchone()
        if row is None:
            return None
        job_id = int(row["id"])
        conn.execute("UPDATE jobs SET status='running', updated_at=? WHERE id=?", (now_ts(), job_id))
        row2 = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row2) if row2 else None


def _sqlite_job_update(db_path: str, job_id: int, status: str, message: str = "", output_path: Optional[str] = None) -> None:
    with _sqlite_conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status=?, updated_at=?, message=?, output_path=? WHERE id=?",
            (status, now_ts(), message, output_path, job_id),
        )


def _sqlite_jobs_recent(db_path: str, limit: int = 50) -> List[Dict[str, Any]]:
    with _sqlite_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]


# ---------------- Postgres backend ----------------


@contextmanager
def _pg_conn(db_ref: str):
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed")
    conn = psycopg2.connect(db_ref)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _pg_init_db(db_ref: str, default_save_videos: bool, default_auto_delete: bool, default_strict_keys: bool) -> None:
    with _pg_conn(db_ref) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pcs (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    stream_key TEXT NOT NULL UNIQUE,
                    created_at BIGINT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS streams (
                    stream_key TEXT PRIMARY KEY,
                    is_live BOOLEAN NOT NULL,
                    last_publish_at BIGINT,
                    last_unpublish_at BIGINT
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id SERIAL PRIMARY KEY,
                    stream_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    message TEXT,
                    output_path TEXT
                );
                """
            )

            # defaults only if missing
            cur.execute(
                "INSERT INTO settings(key, value) VALUES(%s, %s) ON CONFLICT (key) DO NOTHING",
                ("save_videos", "true" if default_save_videos else "false"),
            )
            cur.execute(
                "INSERT INTO settings(key, value) VALUES(%s, %s) ON CONFLICT (key) DO NOTHING",
                ("auto_delete", "true" if default_auto_delete else "false"),
            )
            cur.execute(
                "INSERT INTO settings(key, value) VALUES(%s, %s) ON CONFLICT (key) DO NOTHING",
                ("strict_keys", "true" if default_strict_keys else "false"),
            )


def _pg_setting_get(db_ref: str, key: str, default: str) -> str:
    with _pg_conn(db_ref) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
            row = cur.fetchone()
            return str(row["value"]) if row else default


def _pg_setting_set(db_ref: str, key: str, value: str) -> None:
    with _pg_conn(db_ref) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO settings(key, value) VALUES(%s, %s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                (key, value),
            )


def _pg_settings_all(db_ref: str) -> Dict[str, str]:
    with _pg_conn(db_ref) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT key, value FROM settings")
            rows = cur.fetchall() or []
            return {str(r["key"]): str(r["value"]) for r in rows}


def _pg_pc_create(db_ref: str, name: str) -> Tuple[int, str, str]:
    name = _normalize_name(name)
    base = "".join(ch.lower() for ch in name if ch.isalnum())
    base = base[:12] or "pc"

    for _ in range(10):
        key = generate_stream_key(base)
        try:
            with _pg_conn(db_ref) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO pcs(name, stream_key, created_at) VALUES(%s, %s, %s) RETURNING id",
                        (name, key, now_ts()),
                    )
                    pc_id = int(cur.fetchone()[0])
                    return pc_id, name, key
        except Exception as e:
            # Unique violation
            if psycopg2 is not None and isinstance(e, psycopg2.IntegrityError):
                continue
            raise
    raise RuntimeError("Не удалось сгенерировать уникальный stream_key")


def _pg_pc_list(db_ref: str) -> List[Dict[str, Any]]:
    with _pg_conn(db_ref) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT p.id, p.name, p.stream_key, p.created_at,
                       COALESCE(s.is_live, FALSE) AS is_live,
                       s.last_publish_at, s.last_unpublish_at
                FROM pcs p
                LEFT JOIN streams s ON s.stream_key = p.stream_key
                ORDER BY p.id DESC
                """
            )
            rows = cur.fetchall() or []
            # normalize booleans for templates
            for r in rows:
                r["is_live"] = bool(r.get("is_live"))
            return [dict(r) for r in rows]


def _pg_pc_get(db_ref: str, pc_id: int) -> Optional[Dict[str, Any]]:
    with _pg_conn(db_ref) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT p.id, p.name, p.stream_key, p.created_at,
                       COALESCE(s.is_live, FALSE) AS is_live,
                       s.last_publish_at, s.last_unpublish_at
                FROM pcs p
                LEFT JOIN streams s ON s.stream_key = p.stream_key
                WHERE p.id=%s
                """,
                (pc_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            row["is_live"] = bool(row.get("is_live"))
            return dict(row)


def _pg_pc_by_stream_key(db_ref: str, stream_key: str) -> Optional[Dict[str, Any]]:
    with _pg_conn(db_ref) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, name, stream_key, created_at FROM pcs WHERE stream_key=%s", (stream_key,))
            row = cur.fetchone()
            return dict(row) if row else None


def _pg_stream_set_live(db_ref: str, stream_key: str, is_live: bool) -> None:
    ts = now_ts()
    with _pg_conn(db_ref) as conn:
        with conn.cursor() as cur:
            if is_live:
                cur.execute(
                    """
                    INSERT INTO streams(stream_key, is_live, last_publish_at, last_unpublish_at)
                    VALUES(%s, TRUE, %s, NULL)
                    ON CONFLICT (stream_key) DO UPDATE SET is_live=TRUE, last_publish_at=EXCLUDED.last_publish_at
                    """,
                    (stream_key, ts),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO streams(stream_key, is_live, last_publish_at, last_unpublish_at)
                    VALUES(%s, FALSE, NULL, %s)
                    ON CONFLICT (stream_key) DO UPDATE SET is_live=FALSE, last_unpublish_at=EXCLUDED.last_unpublish_at
                    """,
                    (stream_key, ts),
                )


def _pg_live_streams(db_ref: str) -> List[str]:
    with _pg_conn(db_ref) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT stream_key FROM streams WHERE is_live=TRUE ORDER BY last_publish_at DESC NULLS LAST")
            rows = cur.fetchall() or []
            return [r[0] for r in rows]


def _pg_job_create(db_ref: str, stream_key: str, message: str = "") -> int:
    ts = now_ts()
    with _pg_conn(db_ref) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs(stream_key, status, created_at, updated_at, message) VALUES(%s, 'queued', %s, %s, %s) RETURNING id",
                (stream_key, ts, ts, message),
            )
            return int(cur.fetchone()[0])


def _pg_job_claim_next(db_ref: str) -> Optional[Dict[str, Any]]:
    with _pg_conn(db_ref) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                WITH cte AS (
                    SELECT id FROM jobs
                    WHERE status='queued'
                    ORDER BY id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE jobs
                SET status='running', updated_at=%s
                FROM cte
                WHERE jobs.id = cte.id
                RETURNING jobs.*
                """,
                (now_ts(),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _pg_job_update(db_ref: str, job_id: int, status: str, message: str = "", output_path: Optional[str] = None) -> None:
    with _pg_conn(db_ref) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status=%s, updated_at=%s, message=%s, output_path=%s WHERE id=%s",
                (status, now_ts(), message, output_path, job_id),
            )


def _pg_jobs_recent(db_ref: str, limit: int = 50) -> List[Dict[str, Any]]:
    with _pg_conn(db_ref) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT %s", (int(limit),))
            rows = cur.fetchall() or []
            return [dict(r) for r in rows]


# ---------------- Public API (switching) ----------------


def init_db(db_ref: str, default_save_videos: bool, default_auto_delete: bool, default_strict_keys: bool) -> None:
    if _is_postgres(db_ref):
        _pg_init_db(db_ref, default_save_videos, default_auto_delete, default_strict_keys)
    else:
        _sqlite_init_db(db_ref, default_save_videos, default_auto_delete, default_strict_keys)


def setting_get(db_ref: str, key: str, default: str) -> str:
    return _pg_setting_get(db_ref, key, default) if _is_postgres(db_ref) else _sqlite_setting_get(db_ref, key, default)


def setting_set(db_ref: str, key: str, value: str) -> None:
    if _is_postgres(db_ref):
        _pg_setting_set(db_ref, key, value)
    else:
        _sqlite_setting_set(db_ref, key, value)


def settings_all(db_ref: str) -> Dict[str, str]:
    return _pg_settings_all(db_ref) if _is_postgres(db_ref) else _sqlite_settings_all(db_ref)


def pc_create(db_ref: str, name: str) -> Tuple[int, str, str]:
    return _pg_pc_create(db_ref, name) if _is_postgres(db_ref) else _sqlite_pc_create(db_ref, name)


def pc_list(db_ref: str) -> List[Dict[str, Any]]:
    return _pg_pc_list(db_ref) if _is_postgres(db_ref) else _sqlite_pc_list(db_ref)


def pc_get(db_ref: str, pc_id: int) -> Optional[Dict[str, Any]]:
    return _pg_pc_get(db_ref, pc_id) if _is_postgres(db_ref) else _sqlite_pc_get(db_ref, pc_id)


def pc_by_stream_key(db_ref: str, stream_key: str) -> Optional[Dict[str, Any]]:
    return _pg_pc_by_stream_key(db_ref, stream_key) if _is_postgres(db_ref) else _sqlite_pc_by_stream_key(db_ref, stream_key)


def stream_set_live(db_ref: str, stream_key: str, is_live: bool) -> None:
    if _is_postgres(db_ref):
        _pg_stream_set_live(db_ref, stream_key, is_live)
    else:
        _sqlite_stream_set_live(db_ref, stream_key, is_live)


def live_streams(db_ref: str) -> List[str]:
    return _pg_live_streams(db_ref) if _is_postgres(db_ref) else _sqlite_live_streams(db_ref)


def job_create(db_ref: str, stream_key: str, message: str = "") -> int:
    return _pg_job_create(db_ref, stream_key, message) if _is_postgres(db_ref) else _sqlite_job_create(db_ref, stream_key, message)


def job_claim_next(db_ref: str) -> Optional[Dict[str, Any]]:
    return _pg_job_claim_next(db_ref) if _is_postgres(db_ref) else _sqlite_job_claim_next(db_ref)


def job_update(db_ref: str, job_id: int, status: str, message: str = "", output_path: Optional[str] = None) -> None:
    if _is_postgres(db_ref):
        _pg_job_update(db_ref, job_id, status, message, output_path)
    else:
        _sqlite_job_update(db_ref, job_id, status, message, output_path)


def jobs_recent(db_ref: str, limit: int = 50) -> List[Dict[str, Any]]:
    return _pg_jobs_recent(db_ref, limit) if _is_postgres(db_ref) else _sqlite_jobs_recent(db_ref, limit)
