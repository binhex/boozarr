"""SQLite database for tracking processed EPUB files."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class ProcessingDB:
    """Thread-unsafe SQLite wrapper for boozarr tracking."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS processed_files (
        file_path TEXT PRIMARY KEY,
        file_hash TEXT NOT NULL,
        processed_at TEXT NOT NULL,
        status TEXT NOT NULL,
        issues_found INTEGER DEFAULT 0,
        fixes_applied INTEGER DEFAULT 0,
        dry_run BOOLEAN NOT NULL
    );
    CREATE TABLE IF NOT EXISTS processing_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        processor TEXT NOT NULL,
        action TEXT NOT NULL,
        detail TEXT,
        timestamp TEXT NOT NULL
    );"""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.executescript(self.SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def lookup_hash(self, file_hash: str) -> str | None:
        cursor = self.conn.execute("SELECT status FROM processed_files WHERE file_hash = ?", (file_hash,))
        row = cursor.fetchone()
        return row[0] if row else None

    def record_file(
        self,
        file_path: str,
        file_hash: str,
        status: str,
        issues: int,
        fixes: int,
        dry_run: bool,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO processed_files "
            "(file_path, file_hash, processed_at, status, issues_found, fixes_applied, dry_run) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (file_path, file_hash, now, status, issues, fixes, dry_run),
        )
        self.conn.commit()

    def log_event(self, file_path: str, processor: str, action: str, detail: str) -> None:
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "INSERT INTO processing_log (file_path, processor, action, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
            (file_path, processor, action, detail, now),
        )
        self.conn.commit()
