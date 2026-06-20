"""Tests for Pipeline orchestrator."""

from __future__ import annotations

import hashlib
import zipfile
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from boozarr.pipeline import Pipeline
from boozarr.processors.borders import BordersProcessor

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
    """Integration tests for --fix extract/repack/backup behaviour."""

    def test_fix_extracts_and_repacks(self, tmp_path: Path) -> None:
        """When fix=True, the EPUB should be extracted, processed, and repacked."""
        epub_path = tmp_path / "input.epub"
        _make_epub(epub_path)
        original_hash = _compute_hash(epub_path)

        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        pipeline = Pipeline(db=db, processors=[_ModifyingProcessor()], config={}, fix=True)
        result = pipeline.process_epub(epub_path)

        assert result["status"] != "error", f"Pipeline failed: {result}"
        new_hash = _compute_hash(epub_path)
        assert new_hash != original_hash, "EPUB was not modified: hash unchanged"
        assert result["fixes"] > 0, "No fixes were counted"

    def test_backup_created_by_default_when_fixing(self, tmp_path: Path) -> None:
        """Backup should be ON by default when fix=True (no --no-backup needed)."""
        epub_path = tmp_path / "input.epub"
        _make_epub(epub_path)
        original_content = epub_path.read_bytes()

        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        pipeline = Pipeline(db=db, processors=[_ModifyingProcessor()], config={}, fix=True)
        result = pipeline.process_epub(epub_path)

        assert result["status"] != "error", f"Pipeline failed: {result}"
        bak_path = epub_path.with_suffix(".epub.bak")
        assert bak_path.exists(), f"Backup should exist by default but {bak_path} not found"
        assert bak_path.read_bytes() == original_content, "Backup content differs from original"

    def test_no_backup_when_flag_is_false(self, tmp_path: Path) -> None:
        """When backup=False (--no-backup), no .bak file should be created."""
        epub_path = tmp_path / "input.epub"
        _make_epub(epub_path)

        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        pipeline = Pipeline(db=db, processors=[_ModifyingProcessor()], config={}, fix=True, backup=False)
        result = pipeline.process_epub(epub_path)

        assert result["status"] != "error", f"Pipeline failed: {result}"
        bak_path = epub_path.with_suffix(".epub.bak")
        assert not bak_path.exists(), "Backup file should NOT exist when backup=False"

    def test_no_backup_in_dry_run_even_with_default(self, tmp_path: Path) -> None:
        """No backup should be created in dry-run mode even with default backup=True."""
        epub_path = tmp_path / "input.epub"
        _make_epub(epub_path)

        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        pipeline = Pipeline(db=db, processors=[_ModifyingProcessor()], config={}, fix=False)
        result = pipeline.process_epub(epub_path)

        assert result["status"] != "error", f"Pipeline failed: {result}"
        bak_path = epub_path.with_suffix(".epub.bak")
        assert not bak_path.exists(), "Backup should NOT exist in dry-run mode"

    def test_result_includes_fix_details(self, tmp_path: Path) -> None:
        """The pipeline result should include a list of fix descriptions."""
        epub_path = tmp_path / "input.epub"
        _make_epub(epub_path)

        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        pipeline = Pipeline(db=db, processors=[_ModifyingProcessor()], config={}, fix=True)
        result = pipeline.process_epub(epub_path)

        assert result["status"] != "error", f"Pipeline failed: {result}"
        assert "fix_details" in result, "Result should include fix_details"
        assert isinstance(result["fix_details"], list), "fix_details should be a list"

    def test_fix_details_contains_old_new_values(self, tmp_path: Path) -> None:
        """fix_details should contain old→new format with old_value/new_value."""
        epub_path = tmp_path / "test.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr("OEBPS/style.css", "body { padding: 10px; }")

        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        pipeline = Pipeline(
            db=db,
            processors=[BordersProcessor()],
            config={"padding": "1px"},
            fix=True,
        )
        result = pipeline.process_epub(epub_path)

        assert result["status"] != "error", f"Pipeline failed: {result}"
        details = result["fix_details"]
        assert len(details) > 0, "Expected at least one fix_detail"
        detail = details[0]
        assert "padding" in detail, f"Expected 'padding' in fix_detail, got: {detail}"
        assert "10px" in detail, f"Expected '10px' (old_value) in fix_detail, got: {detail}"
        assert "1px" in detail, f"Expected '1px' (new_value) in fix_detail, got: {detail}"
        assert "→" in detail or "==" in detail, f"Expected '→' or '==' arrow in fix_detail, got: {detail}"


class TestPipelineConfigAwareSkip:
    """Tests that skip logic respects CLI config changes."""

    def _make_epub(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")

    def test_same_config_skips(self, tmp_path: Path) -> None:
        """Same config on same file should skip."""
        from boozarr.db import ProcessingDB

        epub_path = tmp_path / "test.epub"
        self._make_epub(epub_path)

        db = ProcessingDB(tmp_path / "test.db")

        # First run with config A
        p1 = Pipeline(db=db, processors=[], config={"border": "1px"}, fix=True)
        r1 = p1.process_epub(epub_path)
        assert r1["status"] != "error"

        # Second run with same config A — should skip
        p2 = Pipeline(db=db, processors=[], config={"border": "1px"}, fix=True)
        r2 = p2.process_epub(epub_path)
        assert r2["status"] == "skip", f"Same config should skip, got {r2['status']}"

    def test_different_config_does_not_skip(self, tmp_path: Path) -> None:
        """Different config on same file should NOT skip."""
        from boozarr.db import ProcessingDB

        epub_path = tmp_path / "test.epub"
        self._make_epub(epub_path)

        db = ProcessingDB(tmp_path / "test.db")

        # First run with config A
        p1 = Pipeline(db=db, processors=[], config={"border": "1px"}, fix=True)
        r1 = p1.process_epub(epub_path)
        assert r1["status"] != "error"

        # Second run with config B (different border) — should NOT skip
        p2 = Pipeline(db=db, processors=[], config={"border": "100px"}, fix=True)
        r2 = p2.process_epub(epub_path)
        assert r2["status"] != "skip", (
            f"Different config ({r2['status']}) should NOT skip. Bug: config_hash not checked in skip logic!"
        )

    def test_same_config_skips_even_with_warn_status(self, tmp_path: Path) -> None:
        """Same config should skip even when previous run had fixes (status='warn')."""
        from unittest.mock import MagicMock

        from boozarr.db import ProcessingDB

        epub_path = tmp_path / "test.epub"
        self._make_epub(epub_path)

        db = ProcessingDB(tmp_path / "test.db")

        # A processor that returns issues/fixes so the result status is "warn"
        proc = MagicMock()
        proc.name = "test_proc"
        proc.check.return_value = [MagicMock()]
        proc.fix.return_value = [MagicMock()]

        # First run with config A — produces fixes → status 'warn'
        p1 = Pipeline(db=db, processors=[proc], config={"border": "1px"}, fix=True)
        r1 = p1.process_epub(epub_path)
        assert r1["status"] == "warn", f"Expected 'warn' (has fixes), got '{r1['status']}'"

        # Second run with same config A — should SKIP
        p2 = Pipeline(db=db, processors=[proc], config={"border": "1px"}, fix=True)
        r2 = p2.process_epub(epub_path)
        assert r2["status"] == "skip", f"Same config with warn status should skip, got '{r2['status']}'"


class TestPipeline:
    def test_dry_run_does_not_count_fixes(self, tmp_path: Path) -> None:
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
        assert result["dry_run"] is True
        proc.check.assert_called_once()
        proc.fix.assert_called_once()  # Called to generate fix_details, but fixes not counted

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
