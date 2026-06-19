"""Tests for ProcessingDB — SQLite tracking database."""

from __future__ import annotations

from typing import TYPE_CHECKING

from boozarr.db import ProcessingDB

if TYPE_CHECKING:
    from pathlib import Path


class TestProcessingDBInit:
    def test_init_creates_tables(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        tables = {row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "processed_files" in tables
        assert "processing_log" in tables

    def test_init_reuses_existing_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db1 = ProcessingDB(db_path)
        db1.record_file("a.epub", "hash1", "ok", issues=0, fixes=0, dry_run=True)
        db1.close()

        db2 = ProcessingDB(db_path)
        assert db2.lookup_hash("hash1") == "ok"
        db2.close()


class TestProcessingDB:
    def test_lookup_missing_hash(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        assert db.lookup_hash("missing") is None

    def test_lookup_existing_hash(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        db.record_file("a.epub", "abc", "ok", issues=2, fixes=1, dry_run=True)
        assert db.lookup_hash("abc") == "ok"

    def test_record_and_verify(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        db.record_file("book.epub", "def", "ok", issues=0, fixes=3, dry_run=False)
        row = db.conn.execute("SELECT file_path, status, fixes_applied FROM processed_files").fetchone()
        assert row == ("book.epub", "ok", 3)

    def test_log_event(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        db.log_event("book.epub", "chapters", "check", '{"found": 0}')
        row = db.conn.execute("SELECT file_path, processor, action FROM processing_log").fetchone()
        assert row == ("book.epub", "chapters", "check")
