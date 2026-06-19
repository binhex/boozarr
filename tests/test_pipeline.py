"""Tests for Pipeline orchestrator."""

from __future__ import annotations

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
