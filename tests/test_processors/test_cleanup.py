"""Tests for CleanupProcessor."""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.epub import EpubWrapper
from boozarr.processors.cleanup import CleanupProcessor


class TestCleanupCheck:
    def test_no_issues_when_cleanup_not_configured(self) -> None:
        epub = MagicMock()
        assert CleanupProcessor().check(epub) == []

    def test_no_issues_when_config_is_none(self) -> None:
        epub = MagicMock()
        assert CleanupProcessor().check(epub, None) == []

    def test_no_issues_when_extract_missing(self) -> None:
        epub = MagicMock()
        del epub._extract_dir
        assert CleanupProcessor().check(epub, {"cleanup": True}) == []

    def test_detects_empty_paragraphs(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr(
                "OEBPS/chapter1.xhtml",
                "<html><body><p></p><p>Text</p><p> </p></body></html>",
            )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = CleanupProcessor().check(wrapper, {"cleanup": True})
        assert len(issues) >= 1


class TestCleanupFix:
    def test_fix_without_extract_returns_empty(self) -> None:
        epub = MagicMock()
        assert CleanupProcessor().fix(epub, [], {}) == []

    def test_fix_strips_nbsp_and_empty_in_one_pass(self, tmp_path: Path) -> None:
        """nbsp-filled elements should be fully stripped in a single fix() call."""
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            # &nbsp; inside empty p/div tags — should all be removed in one pass
            zf.writestr(
                "OEBPS/ch1.xhtml",
                "<html><body>"
                "<p>Hello</p>"
                "<p>&nbsp;&nbsp;&nbsp;</p>"
                "<div>&nbsp;</div>"
                "<p>World</p>"
                "<span>&nbsp;</span>"
                "</body></html>",
            )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = CleanupProcessor().check(wrapper, {"cleanup": True})
        assert len(issues) >= 1
        fixes = CleanupProcessor().fix(wrapper, issues, {"cleanup": True})
        assert len(fixes) >= 1
        result = (extract_dir / "OEBPS/ch1.xhtml").read_text()
        # All nbsp-filled tags should be gone
        assert "&nbsp;" not in result, "nbsp entities should be stripped"
        assert "<p></p>" not in result, "empty p tags should be removed"
        assert "<div></div>" not in result, "empty div tags should be removed"
        assert "<span></span>" not in result, "empty span tags should be removed"
        assert "<p>Hello</p>" in result
        assert "<p>World</p>" in result

    def test_fix_strips_empty_elements(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr(
                "OEBPS/ch1.xhtml",
                "<html><body><p>Hello</p><p></p><div> </div><p>World</p><span></span></body></html>",
            )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = CleanupProcessor().check(wrapper, {"cleanup": True})
        assert len(issues) >= 1
        fixes = CleanupProcessor().fix(wrapper, issues, {"cleanup": True})
        assert len(fixes) >= 1
        # Verify empty elements removed
        result = (extract_dir / "OEBPS/ch1.xhtml").read_text()
        assert "<p></p>" not in result
        assert "<div> </div>" not in result
        assert "<span></span>" not in result
        assert "<p>Hello</p>" in result
        assert "<p>World</p>" in result

    def test_fix_aggregates_nbsp_across_files(self, tmp_path: Path) -> None:
        """fix() returns a single aggregated Fix for leading nbsp across
        multiple XHTML files, not one Fix per file."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        # 3 files, each with 1 leading-nbsp match = 3 total
        for i in range(1, 4):
            (extract_dir / f"ch{i}.xhtml").write_text("<html><body><p>&nbsp;&nbsp;Text.</p></body></html>")

        epub = MagicMock()
        epub._extract_dir = extract_dir

        processor = CleanupProcessor()
        issues = processor.check(epub, {"cleanup": True})
        fixes = processor.fix(epub, issues, {"cleanup": True})

        # Should return 1 aggregated Fix, not 3 per-file Fixes
        assert len(fixes) == 1, (
            f"Expected 1 aggregated Fix, got {len(fixes)} — cleanup produces too many log lines per-file"
        )
        # Aggregated Fix must use empty old/new → concise format in pipeline
        assert fixes[0].old_value == "", (
            "Aggregated fix should have empty old_value so _format_fix_detail uses the concise description-only path"
        )
        assert fixes[0].new_value == "", (
            "Aggregated fix should have empty new_value so _format_fix_detail uses the concise description-only path"
        )
        # Description aggregator counts _LEADING_NBSP_RE matches, not
        # individual &nbsp; characters (the regex uses + so contiguous
        # nbsp count as one match per opening tag)
        desc = fixes[0].description
        assert "3" in desc, f"Expected leading-nbsp match count 3 in description: {desc}"
        assert "3 files" in desc, f"Expected file count in description: {desc}"

    def test_fix_aggregates_mixed_nbsp_and_empty_tags(self, tmp_path: Path) -> None:
        """fix() aggregates both leading nbsp and empty tag removals."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        # File 1: 1 leading-nbsp match (3 &nbsp; are one contiguous group)
        (extract_dir / "ch1.xhtml").write_text("<html><body><p>&nbsp;&nbsp;&nbsp;Text.</p></body></html>")
        # File 2: 2 empty element matches
        (extract_dir / "ch2.xhtml").write_text("<html><body><p>Hi</p><p></p><span></span></body></html>")
        # File 3: 1 nbsp match + 1 empty element match
        (extract_dir / "ch3.xhtml").write_text("<html><body><p>&nbsp;Text</p><div></div></body></html>")

        epub = MagicMock()
        epub._extract_dir = extract_dir

        processor = CleanupProcessor()
        issues = processor.check(epub, {"cleanup": True})
        fixes = processor.fix(epub, issues, {"cleanup": True})

        # Should be a single aggregated Fix
        assert len(fixes) == 1
        desc = fixes[0].description
        # nbsp matches: 1 from ch1 + 1 from ch3 = 2
        assert "2" in desc, f"Expected nbsp match count 2 in description: {desc}"
        # empty tag matches: 2 from ch2 + 1 from ch3 = 3
        assert "3" in desc, f"Expected empty tag count 3 in description: {desc}"
        assert "3 files" in desc, f"Expected file count in description: {desc}"

    def test_fix_and_check_on_clean_file_returns_empty(self, tmp_path: Path) -> None:
        """fix() returns empty list when no XHTML files have issues."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        (extract_dir / "clean.xhtml").write_text("<html><body><p>Hello</p><p>World</p></body></html>")

        epub = MagicMock()
        epub._extract_dir = extract_dir

        processor = CleanupProcessor()
        # check on clean file returns no per-file issues (only summary if any)
        issues = processor.check(epub, {"cleanup": True})
        assert len(issues) == 0, "Expected 0 issues for clean file"
        # fix on clean file returns empty — no changes needed
        fixes = processor.fix(epub, [], {"cleanup": True})
        assert fixes == [], f"Expected empty fix list for clean file, got {fixes}"
