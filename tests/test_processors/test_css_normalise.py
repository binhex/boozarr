"""Tests for CssNormaliseProcessor."""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

from boozarr.epub import EpubWrapper

if TYPE_CHECKING:
    from pathlib import Path
from boozarr.processors.css_normalise import CssNormaliseProcessor


class TestCssNormaliseEdgeCases:
    def test_check_without_extract_returns_empty(self) -> None:
        from unittest.mock import MagicMock

        issues = CssNormaliseProcessor().check(MagicMock())
        assert issues == []

    def test_fix_without_extract_returns_empty(self) -> None:
        from unittest.mock import MagicMock

        fixes = CssNormaliseProcessor().fix(MagicMock(), [], {})
        assert fixes == []

    def test_detects_issues_from_inline_styles(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "inline.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr(
                "OEBPS/ch1.xhtml",
                "<html><head><style>body { font-size: 3em; }</style></head><body><p>Hi</p></body></html>",
            )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = CssNormaliseProcessor().check(wrapper)
        assert len(issues) >= 1

    def test_fix_preserves_css_comments(self, tmp_path: Path) -> None:
        css_content = """/* header */
p { font-size: 3em; /* inline comment */ line-height: 2.5; }
/* footer */"""
        epub_path = tmp_path / "comments.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr("OEBPS/styles.css", css_content)
            zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Text</p></body></html>")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        processor = CssNormaliseProcessor()
        issues = processor.check(wrapper)
        assert len(issues) >= 1
        fixes = processor.fix(wrapper, issues, {"font_size": "1em", "line_height": "1.5"})
        assert len(fixes) >= 1
        wrapper.repack(epub_path)
        with zipfile.ZipFile(epub_path, "r") as zf:
            css = zf.read("OEBPS/styles.css").decode()
        assert "/* header */" in css
        assert "/* inline comment */" in css
        assert "/* footer */" in css
        assert "font-size: 1em" in css
        assert "3em" not in css


class TestCssNormaliseProcessorIntegration:
    """Integration tests using real EPUBs with CSS files."""

    def _make_epub_with_css(self, path: Path, css_content: str) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "content.opf",
                '<?xml version="1.0" encoding="UTF-8"?><package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>Test</dc:title></metadata></package>',
            )
            zf.writestr("OEBPS/styles.css", css_content)
            zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Text</p></body></html>")

    def test_no_issues_when_standard(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(epub_path, "body { font-size: 1em; line-height: 1.5; text-align: left; }")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = CssNormaliseProcessor().check(wrapper)
        assert issues == []

    def test_issue_on_nonstandard_font_size(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(epub_path, "body { font-size: 2em; line-height: 1.5; }")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = CssNormaliseProcessor().check(wrapper)
        assert len(issues) == 1

    def test_fix_applies_values(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(epub_path, "body { font-size: 2em; line-height: 2; }")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        processor = CssNormaliseProcessor()
        issues = processor.check(wrapper)
        assert len(issues) >= 1
        fixes = processor.fix(wrapper, issues, {"font_size": "1em", "line_height": "1.5"})
        assert len(fixes) >= 1
        wrapper.repack(epub_path)
        with zipfile.ZipFile(epub_path, "r") as zf:
            css = zf.read("OEBPS/styles.css").decode()
        assert "font-size: 1em" in css
        assert "line-height: 1.5" in css

    def test_fix_returns_correct_old_and_new_values(self, tmp_path: Path) -> None:
        """Fix.old_value should be the parsed CSS value, new_value the configured target."""
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(epub_path, "body { font-size: 2em; line-height: 2; }")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        processor = CssNormaliseProcessor()
        issues = processor.check(wrapper)
        assert len(issues) >= 1
        fixes = processor.fix(wrapper, issues, {"font_size": "1em", "line_height": "1.5"})
        assert len(fixes) >= 1

        for fix in fixes:
            if "font-size" in fix.location:
                assert fix.old_value == "2em"
                assert fix.new_value == "1em"
            elif "line-height" in fix.location:
                assert fix.old_value == "2"
                assert fix.new_value == "1.5"
