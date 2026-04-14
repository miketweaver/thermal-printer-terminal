import json
import os
from datetime import datetime, timezone

import aiosqlite

from app.config import settings
from app.theme import resolve_hostname

_db_path = settings.DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS print_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type      TEXT NOT NULL,
    submitted_at  TEXT NOT NULL DEFAULT (datetime('now')),
    submitted_by  TEXT,
    content       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'queued',
    started_at    TEXT,
    completed_at  TEXT,
    error_message TEXT,
    retry_count   INTEGER NOT NULL DEFAULT 0,
    has_image     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON print_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_submitted ON print_jobs(submitted_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


async def _get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(_db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    os.makedirs(os.path.dirname(_db_path) or ".", exist_ok=True)
    db = await _get_db()
    try:
        await db.executescript(SCHEMA)
        # Migrate: add has_image column if missing
        try:
            await db.execute("SELECT has_image FROM print_jobs LIMIT 1")
        except Exception:
            await db.execute("ALTER TABLE print_jobs ADD COLUMN has_image INTEGER NOT NULL DEFAULT 0")
        await db.commit()
    finally:
        await db.close()
    # Ensure image storage directory exists
    os.makedirs(os.path.join(os.path.dirname(_db_path) or ".", "images"), exist_ok=True)


async def get_setting(key: str, default: str = "") -> str:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else default
    finally:
        await db.close()


async def set_setting(key: str, value: str):
    db = await _get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()
    finally:
        await db.close()


async def get_all_settings() -> dict:
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        await db.close()


async def enqueue_job(job_type: str, submitted_by: str, content: dict, has_image: bool = False) -> int:
    # Resolve hostname at submission time so the log is permanent
    hostname = resolve_hostname(submitted_by)
    if hostname:
        submitted_by = f'{submitted_by} ({hostname})'

    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO print_jobs (job_type, submitted_by, content, submitted_at, has_image) VALUES (?, ?, ?, ?, ?)",
            (job_type, submitted_by, json.dumps(content), datetime.now(timezone.utc).isoformat(), int(has_image)),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_next_queued_job():
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM print_jobs WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
        )
        return await cursor.fetchone()
    finally:
        await db.close()


async def update_job_status(job_id: int, status: str, error_message: str = None):
    db = await _get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        if status == "printing":
            await db.execute(
                "UPDATE print_jobs SET status = ?, started_at = ? WHERE id = ?",
                (status, now, job_id),
            )
        elif status == "done":
            await db.execute(
                "UPDATE print_jobs SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, job_id),
            )
        elif status == "failed":
            await db.execute(
                "UPDATE print_jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?",
                (status, error_message, now, job_id),
            )
        else:
            await db.execute(
                "UPDATE print_jobs SET status = ?, error_message = ? WHERE id = ?",
                (status, error_message, job_id),
            )
        await db.commit()
    finally:
        await db.close()


async def increment_retry(job_id: int):
    db = await _get_db()
    try:
        await db.execute(
            "UPDATE print_jobs SET retry_count = retry_count + 1 WHERE id = ?",
            (job_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def get_recent_jobs(limit: int = 50):
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM print_jobs ORDER BY id DESC LIMIT ?", (limit,)
        )
        return await cursor.fetchall()
    finally:
        await db.close()


async def get_failed_jobs():
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM print_jobs WHERE status = 'failed' ORDER BY id DESC"
        )
        return await cursor.fetchall()
    finally:
        await db.close()


async def get_queue_depth() -> int:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM print_jobs WHERE status = 'queued'"
        )
        row = await cursor.fetchone()
        return row[0]
    finally:
        await db.close()


async def get_job_by_id(job_id: int):
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM print_jobs WHERE id = ?", (job_id,)
        )
        return await cursor.fetchone()
    finally:
        await db.close()


async def delete_job(job_id: int):
    db = await _get_db()
    try:
        await db.execute("DELETE FROM print_jobs WHERE id = ?", (job_id,))
        await db.commit()
    finally:
        await db.close()


async def requeue_job(job_id: int):
    db = await _get_db()
    try:
        await db.execute(
            "UPDATE print_jobs SET status = 'queued', error_message = NULL, "
            "started_at = NULL, completed_at = NULL, retry_count = 0 WHERE id = ?",
            (job_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def mark_job_has_image(job_id: int):
    db = await _get_db()
    try:
        await db.execute(
            "UPDATE print_jobs SET has_image = 1 WHERE id = ?", (job_id,)
        )
        await db.commit()
    finally:
        await db.close()


async def get_job_stats() -> dict:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT status, COUNT(*) as cnt FROM print_jobs GROUP BY status"
        )
        rows = await cursor.fetchall()
        stats = {row["status"]: row["cnt"] for row in rows}
        return stats
    finally:
        await db.close()
