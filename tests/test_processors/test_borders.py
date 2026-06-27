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


class TestBordersTargetMap:
    """Tests for _build_target_map value normalization."""

    def test_bare_number_gets_px(self) -> None:
        tm = BordersProcessor._build_target_map({"margin": "50"})
        assert tm["margin"] == "50px"
        assert tm["margin-left"] == "50px"
        assert tm["margin-right"] == "50px"
        assert tm["margin-top"] == "50px"
        assert tm["margin-bottom"] == "50px"

    def test_number_with_unit_passes_through(self) -> None:
        tm = BordersProcessor._build_target_map({"margin": "2em"})
        assert tm["margin"] == "2em"

    def test_zero_no_unit(self) -> None:
        tm = BordersProcessor._build_target_map({"margin": "0"})
        assert tm["margin"] == "0"

    def test_none_skipped(self) -> None:
        tm = BordersProcessor._build_target_map({"border": None, "margin": "10"})
        assert "border" not in tm
        assert tm["margin"] == "10px"

    def test_non_numeric_passes_through(self) -> None:
        tm = BordersProcessor._build_target_map({"border": "none"})
        assert tm["border"] == "none"

    def test_all_length_properties_normalized(self) -> None:
        """border, margin, padding all get px appended to bare numbers."""
        tm = BordersProcessor._build_target_map({"border": "5", "margin": "10", "padding": "20"})
        assert tm["border"] == "5px"
        assert tm["margin"] == "10px"
        assert tm["margin-left"] == "10px"
        assert tm["margin-right"] == "10px"
        assert tm["margin-top"] == "10px"
        assert tm["margin-bottom"] == "10px"
        assert tm["padding"] == "20px"

    # ── Per-side margin/padding override tests ──────────────────────────

    def test_per_side_margin_override(self) -> None:
        """When margin and margin_top are both specified, margin_top
        overrides the margin-top value."""
        tm = BordersProcessor._build_target_map({"margin": "10", "margin_top": "5"})
        assert tm["margin"] == "10px"
        assert tm["margin-left"] == "10px"
        assert tm["margin-right"] == "10px"
        assert tm["margin-top"] == "5px"  # overridden by per-side value
        assert tm["margin-bottom"] == "10px"

    def test_per_side_padding_override(self) -> None:
        """When padding and padding_left are both specified, padding_left
        overrides the padding-left value."""
        tm = BordersProcessor._build_target_map({"padding": "10", "padding_left": "5"})
        assert tm["padding"] == "10px"
        assert tm["padding-left"] == "5px"  # overridden
        assert tm["padding-right"] == "10px"
        assert tm["padding-top"] == "10px"  # from shorthand
        assert tm["padding-bottom"] == "10px"  # from shorthand

    def test_per_side_margin_alone(self) -> None:
        """When only margin_top is set (no base margin), only margin-top
        appears in the target map."""
        tm = BordersProcessor._build_target_map({"margin_top": "5"})
        assert tm == {"margin-top": "5px"}

    def test_per_side_padding_alone(self) -> None:
        """When only padding_bottom is set (no base padding), only
        padding-bottom appears in the target map."""
        tm = BordersProcessor._build_target_map({"padding_bottom": "8"})
        assert tm == {"padding-bottom": "8px"}

    def test_per_side_multiple(self) -> None:
        """Multiple per-side overrides can be set simultaneously without
        a base margin or padding."""
        tm = BordersProcessor._build_target_map(
            {
                "margin_top": "3",
                "margin_bottom": "4",
                "padding_left": "1",
                "padding_right": "2",
            }
        )
        assert tm == {
            "margin-top": "3px",
            "margin-bottom": "4px",
            "padding-left": "1px",
            "padding-right": "2px",
        }

    def test_per_side_none_skipped_with_base(self) -> None:
        """When a per-side value is None and the base property is set, the
        base value is preserved (not overridden)."""
        tm = BordersProcessor._build_target_map({"margin": "10", "margin_top": None})
        assert tm["margin"] == "10px"
        assert tm["margin-top"] == "10px"  # falls back to base margin value
        assert tm["margin-bottom"] == "10px"

    def test_per_side_none_without_base(self) -> None:
        """When a per-side value is None and base property is also None,
        nothing is added to the target map."""
        tm = BordersProcessor._build_target_map({"margin_top": None})
        assert tm == {}
