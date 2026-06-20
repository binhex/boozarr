"""Tests for BordersProcessor."""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

from boozarr.epub import EpubWrapper
from boozarr.processors.borders import BordersProcessor

if TYPE_CHECKING:
    from pathlib import Path

    from boozarr.processors.base import Fix


class TestBordersProcessorEdgeCases:
    def test_check_without_extract_returns_empty(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
        wrapper = EpubWrapper(epub_path)
        issues = BordersProcessor().check(wrapper, {})
        assert issues == []

    def test_fix_without_extract_returns_empty(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
        wrapper = EpubWrapper(epub_path)
        fixes = BordersProcessor().fix(wrapper, [], {})
        assert fixes == []

    def test_detects_issues_from_inline_styles(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "inline.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr(
                "OEBPS/ch1.xhtml",
                "<html><head><style>body { border: 5px solid red; }</style></head><body><p>Hi</p></body></html>",
            )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = BordersProcessor().check(wrapper, {"border": "none"})
        assert len(issues) >= 1
        assert any("border" in i.description for i in issues)

    def test_fix_preserves_css_comments(self, tmp_path: Path) -> None:
        css_content = """/* header comment */
body { border: 5px solid red; /* inline comment */ margin: 3cm; }
/* footer comment */"""
        epub_path = tmp_path / "comments.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr("OEBPS/styles.css", css_content)
            zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Text</p></body></html>")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        processor = BordersProcessor()
        issues = processor.check(wrapper, {"border": "none", "margin": "0"})
        assert len(issues) >= 1
        fixes = processor.fix(wrapper, issues, {"border": "none", "margin": "0"})
        assert len(fixes) >= 1
        wrapper.repack(epub_path)
        with zipfile.ZipFile(epub_path, "r") as zf:
            css = zf.read("OEBPS/styles.css").decode()
        assert "/* header comment */" in css
        assert "/* inline comment */" in css
        assert "/* footer comment */" in css
        assert "border: none" in css
        assert "5px" not in css


class TestBordersProcessorIntegration:
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

    def test_no_issues_for_standard_css(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(epub_path, "body { border: none; margin: 1em; padding: 0; }")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = BordersProcessor().check(wrapper, {"border": "none", "margin": "1em", "padding": "0"})
        assert issues == [], f"Expected 0 issues for standard CSS, got {len(issues)}"

    def test_issue_on_nonstandard_border(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(epub_path, "body { border: 2px solid red; margin: 1em; padding: 0; }")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = BordersProcessor().check(wrapper, {"border": "none"})
        assert len(issues) >= 1

    def test_no_issue_when_value_matches_target(self, tmp_path: Path) -> None:
        """When current CSS value equals configured target, no issue should be reported."""
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(
            epub_path,
            "body { border: 5px solid red; margin: 3cm; padding: 1; }",
        )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        # padding=1 matches CSS value of 1 → no issue for padding
        config = {"border": "none", "padding": "1"}
        issues = BordersProcessor().check(wrapper, config)
        prop_names = {i.location.split()[-1].strip("()") for i in issues}
        assert "padding" not in prop_names, f"padding should not be an issue when value==target, got {prop_names}"
        assert "padding-left" not in prop_names, "padding-left should not be an issue when value==target"
        assert "padding-right" not in prop_names, "padding-right should not be an issue when value==target"
        assert "border" in prop_names, "border should still be an issue (5px != none)"

    def test_check_only_reports_configured_properties(self, tmp_path: Path) -> None:
        """When only --margin and --padding are configured, check() must NOT report border."""
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(
            epub_path,
            "body { border: 5px solid red; margin: 3cm; padding: 10px; }",
        )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        # Only margin and padding configured — border should NOT be reported
        config = {"margin": "0", "padding": "0"}
        issues = BordersProcessor().check(wrapper, config)
        prop_names = {i.location.split()[-1].strip("()") for i in issues}
        assert "border" not in prop_names, f"border should not be reported when not configured, got {prop_names}"
        assert "margin" in prop_names, "margin should be reported"
        assert "padding" in prop_names, "padding should be reported"

    def test_all_none_config_reports_nothing(self, tmp_path: Path) -> None:
        """When no properties are configured (all-None dict), check() reports nothing."""
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(
            epub_path,
            "body { border: 2px solid red; margin: 3cm; padding: 10px; }",
        )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        # CLI-default config — all values None
        config = {"border": None, "margin": None, "padding": None}
        issues = BordersProcessor().check(wrapper, config)
        assert issues == [], f"Expected 0 issues when nothing configured, got {len(issues)}"

    def test_issue_on_nonstandard_margin(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(epub_path, "body { margin: 2cm; border: none; padding: 0; }")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        issues = BordersProcessor().check(wrapper, {"margin": "0"})
        assert len(issues) >= 1

    def test_fix_normalises_border(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(epub_path, "body { border: 5px dashed blue; margin: 3cm; }")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        processor = BordersProcessor()
        issues = processor.check(wrapper, {"border": "1px", "margin": "0"})
        assert len(issues) >= 1
        fixes = processor.fix(wrapper, issues, {"border": "1px", "margin": "0"})
        assert len(fixes) >= 1
        wrapper.repack(epub_path)
        with zipfile.ZipFile(epub_path, "r") as zf:
            css = zf.read("OEBPS/styles.css").decode()
        assert "1px" in css
        assert "5px" not in css

    def test_fix_only_applies_specified_options(self, tmp_path: Path) -> None:
        """When only --padding is specified, border and margin should NOT be changed."""
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(
            epub_path,
            "body { border: 5px solid red; margin: 3cm; padding: 5px; }",
        )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        processor = BordersProcessor()
        issues = processor.check(wrapper, {"padding": "10"})
        assert len(issues) >= 1
        # Only specify padding — border and margin should be left alone
        fixes = processor.fix(wrapper, issues, {"padding": "10"})
        assert len(fixes) >= 1
        wrapper.repack(epub_path)
        with zipfile.ZipFile(epub_path, "r") as zf:
            css = zf.read("OEBPS/styles.css").decode()
        assert "padding: 10" in css, "padding should be updated"
        assert "5px solid red" in css, "border should NOT be changed"
        assert "3cm" in css, "margin should NOT be changed"

    def test_fix_populates_old_and_new_values(self, tmp_path: Path) -> None:
        """Fix objects returned by fix() should have correct old_value and new_value."""
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_css(
            epub_path,
            "body { border: 5px dashed blue; margin: 3cm; padding: 10px; }",
        )
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        processor = BordersProcessor()
        issues = processor.check(wrapper, {"border": "none", "margin": "0", "padding": "0"})
        assert len(issues) >= 1
        fixes = processor.fix(wrapper, issues, {"border": "none", "margin": "0", "padding": "0"})
        assert len(fixes) >= 1

        # Build a dict of location -> fix for easy lookup
        fix_by_location: dict[str, Fix] = {}
        for f in fixes:
            fix_by_location[f.location] = f

        # Verify border fix
        assert "CSS (border)" in fix_by_location
        assert fix_by_location["CSS (border)"].old_value == "5px dashed blue"
        assert fix_by_location["CSS (border)"].new_value == "none"

        # Verify margin fix
        assert "CSS (margin)" in fix_by_location
        assert fix_by_location["CSS (margin)"].old_value == "3cm"
        assert fix_by_location["CSS (margin)"].new_value == "0"

        # Verify padding fix
        assert "CSS (padding)" in fix_by_location
        assert fix_by_location["CSS (padding)"].old_value == "10px"
        assert fix_by_location["CSS (padding)"].new_value == "0"
