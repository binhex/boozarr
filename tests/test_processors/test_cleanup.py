"""Tests for CleanupProcessor."""

import zipfile
from pathlib import Path
from unittest.mock import MagicMock

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
