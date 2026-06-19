"""Tests for Pipeline orchestrator."""

from __future__ import annotations

import hashlib
import zipfile
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from boozarr.pipeline import Pipeline

if TYPE_CHECKING:
    from pathlib import Path


def _make_epub(path: Path) -> None:
    """Create a minimal valid EPUB (ZIP with EPUB structure)."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/container.xml", "<container/>")
        zf.writestr("OEBPS/content.opf", "<package/>")


def _compute_hash(path: Path) -> str:
    """Compute SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _ModifyingProcessor:
    """A test processor whose fix() actually modifies the EPUB content."""

    name = "modifier"

    def check(self, epub: object) -> list:
        return [MagicMock()]

    def fix(self, epub: object, issues: list, config: dict) -> list:
        if hasattr(epub, "_extract_dir") and epub._extract_dir:
            marker = epub._extract_dir / "BOOZARR_MODIFIED"
            epub._extract_dir.mkdir(parents=True, exist_ok=True)
            marker.write_text("modified")
        return [MagicMock()]


class TestPipelineFixBehaviour:
    """Integration tests for --fix extract/repack behaviour."""

    def test_fix_extracts_and_repacks(self, tmp_path: Path) -> None:
        """When fix=True, the EPUB should be extracted, processed, and repacked."""
        epub_path = tmp_path / "input.epub"
        _make_epub(epub_path)
        original_hash = _compute_hash(epub_path)

        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        pipeline = Pipeline(
            db=db,
            processors=[_ModifyingProcessor()],
            config={},
            fix=True,
        )
        result = pipeline.process_epub(epub_path)

        assert result["status"] != "error", f"Pipeline failed: {result}"
        new_hash = _compute_hash(epub_path)
        assert new_hash != original_hash, f"EPUB was not modified: hash {original_hash} unchanged after --fix"
        assert result["fixes"] > 0, "No fixes were counted"

    def test_fix_with_backup_creates_bak(self, tmp_path: Path) -> None:
        """When backup=True and fix=True, a .bak copy of the original should exist."""
        epub_path = tmp_path / "input.epub"
        _make_epub(epub_path)
        original_content = epub_path.read_bytes()

        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        pipeline = Pipeline(
            db=db,
            processors=[_ModifyingProcessor()],
            config={},
            fix=True,
            backup=True,
        )
        result = pipeline.process_epub(epub_path)

        assert result["status"] != "error", f"Pipeline failed: {result}"
        bak_path = epub_path.with_suffix(".epub.bak")
        assert bak_path.exists(), f"Backup file {bak_path} not found"
        assert bak_path.read_bytes() == original_content, "Backup content differs from original"

    def test_backup_not_created_in_dry_run(self, tmp_path: Path) -> None:
        """When backup=True but fix=False, no .bak file should be created."""
        epub_path = tmp_path / "input.epub"
        _make_epub(epub_path)

        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        pipeline = Pipeline(
            db=db,
            processors=[_ModifyingProcessor()],
            config={},
            fix=False,
            backup=True,
        )
        result = pipeline.process_epub(epub_path)

        assert result["status"] != "error", f"Pipeline failed: {result}"
        bak_path = epub_path.with_suffix(".epub.bak")
        assert not bak_path.exists(), f"Backup file {bak_path} should NOT exist in dry-run mode"


class TestPipeline:
    def test_dry_run_does_not_fix(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        _make_epub(epub_path)
        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        proc = MagicMock()
        proc.name = "test"
        proc.check.return_value = [MagicMock()]
        proc.fix.return_value = [MagicMock()]

        pipeline = Pipeline(db=db, processors=[proc], config={}, fix=False)
        result = pipeline.process_epub(epub_path)

        assert result["issues"] == 1
        assert result["fixes"] == 0
        proc.check.assert_called_once()
        proc.fix.assert_not_called()

    def test_fix_mode_applies_fixes(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        _make_epub(epub_path)
        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        proc = MagicMock()
        proc.name = "test"
        proc.check.return_value = [MagicMock()]
        proc.fix.return_value = [MagicMock()]

        pipeline = Pipeline(db=db, processors=[proc], config={}, fix=True)
        result = pipeline.process_epub(epub_path)

        assert result["issues"] == 1
        assert result["fixes"] == 1
        proc.fix.assert_called_once()

    def test_skips_unchanged_file(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        _make_epub(epub_path)
        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = "ok"

        proc = MagicMock()
        pipeline = Pipeline(db=db, processors=[proc], config={}, fix=False)
        result = pipeline.process_epub(epub_path)

        assert result["status"] == "skip"
        proc.check.assert_not_called()

    def test_catches_processor_exception(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        _make_epub(epub_path)
        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        proc = MagicMock()
        proc.name = "crash"
        proc.check.side_effect = RuntimeError("boom")

        pipeline = Pipeline(db=db, processors=[proc], config={}, fix=False)
        result = pipeline.process_epub(epub_path)

        assert result["status"] == "error"
