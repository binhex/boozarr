"""Tests for CompatProcessor."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.processors.base import Issue
from boozarr.processors.compat import CompatProcessor


class TestCompatCheck:
    """Test suite for CompatProcessor.check()."""

    def test_no_fonts_returns_empty(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            "</manifest></package>"
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert issues == []

    def test_detects_embedded_fonts(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="f1" href="fonts/body.otf" media-type="application/x-font-otf"/>'
            '<item id="f2" href="fonts/title.ttf" media-type="application/x-font-ttf"/>'
            "</manifest></package>"
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert len(issues) == 2
        assert all(i.fix_possible for i in issues)
        assert "body.otf" in issues[0].description
        assert "title.ttf" in issues[1].description

    def test_ignores_woff2_fonts(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="f1" href="fonts/body.woff2" media-type="font/woff2"/>'
            "</manifest></package>"
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert issues == []

    def test_skips_when_normalise_not_set(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="f1" href="fonts/body.otf" media-type="application/x-font-otf"/>'
            "</manifest></package>"
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {})
        assert issues == []

    def test_handles_corrupt_opf(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        epub.read_file.return_value = "<<<garbage>>>"
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert issues == []

    def test_detects_apple_display_options(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="ado" href="META-INF/com.apple.ibooks.display-options.xml" '
            'media-type="application/xhtml+xml"/>'
            "</manifest></package>"
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert len(issues) == 1
        assert "apple" in issues[0].description.lower()

    def test_detects_namespace_prefixed_opf_tags(self) -> None:
        """OPF with namespace-prefixed tags like <ns0:package> should
        produce a compat issue."""
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ns0:package xmlns:ns0="http://www.idpf.org/2007/opf" version="2.0">'
            "<ns0:manifest>"
            '<ns0:item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            "</ns0:manifest>"
            "</ns0:package>"
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert len(issues) >= 1
        ns_issues = [i for i in issues if "namespace" in i.description.lower()]
        assert len(ns_issues) == 1, f"Expected 1 namespace issue, got {len(ns_issues)}"

    def test_check_namespace_prefixed_opf_no_opftag_no_issue(self) -> None:
        """OPF with namespaced elements but NOT in the OPF namespace should
        not produce a namespace-prefixed issue."""
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<metadata><dc:title>Test</dc:title></metadata>"
            "<manifest>"
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            "</manifest></package>"
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {"normalise": True})
        ns_issues = [i for i in issues if "namespace" in i.description.lower()]
        assert ns_issues == []


class TestCompatFix:
    """Test suite for CompatProcessor.fix()."""

    def test_removes_font_files_from_disk(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        (extract_dir / "fonts").mkdir()
        font_file = extract_dir / "fonts" / "body.otf"
        font_file.write_text("fake font data")

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="f1" href="fonts/body.otf" media-type="application/x-font-otf"/>'
            "</manifest></package>"
        )

        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="font: fonts/body.otf",
                description="Embedded font found: fonts/body.otf",
                fix_possible=True,
            )
        ]
        fixes = CompatProcessor().fix(epub, issues, {"normalise": True})
        assert len(fixes) >= 1
        assert not font_file.exists()

    def test_removes_apple_display_options(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        meta_inf = extract_dir / "META-INF"
        meta_inf.mkdir()
        ado_file = meta_inf / "com.apple.ibooks.display-options.xml"
        ado_file.write_text("<display_options/>")
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="ado" href="META-INF/com.apple.ibooks.display-options.xml" '
            'media-type="application/xhtml+xml"/>'
            "</manifest></package>"
        )

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"
        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="meta: META-INF/com.apple.ibooks.display-options.xml",
                description="Apple Books display options found",
                fix_possible=True,
            )
        ]
        fixes = CompatProcessor().fix(epub, issues, {"normalise": True})
        assert len(fixes) >= 1
        assert not ado_file.exists()

    def test_fix_without_extract_dir_returns_empty(self) -> None:
        epub = MagicMock()
        epub._extract_dir = None
        epub.get_opf_path.return_value = "content.opf"
        fixes = CompatProcessor().fix(epub, [], {"normalise": True})
        assert fixes == []


class TestCompatNormaliseOpf:
    """Test suite for OPF namespace normalisation."""

    def test_normalises_namespaced_opf(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ns0:package xmlns:ns0="http://www.idpf.org/2007/opf" version="2.0">\n'
            "<ns0:manifest>\n"
            '<ns0:item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>\n'
            "</ns0:manifest>\n"
            '<ns0:spine toc="ncx">\n'
            '<ns0:itemref idref="ch1"/>\n'
            "</ns0:spine>\n"
            "</ns0:package>\n"
        )

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        CompatProcessor().fix(epub, [], {"normalise": True})

        result = opf_path.read_text()
        assert "<ns0:" not in result, f"Namespace prefixes remain: {result[:200]}"
        assert "<itemref" in result
        assert 'xmlns="http://www.idpf.org/2007/opf"' in result

    def test_normalised_opf_preserves_content(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ns0:package xmlns:ns0="http://www.idpf.org/2007/opf" version="2.0">\n'
            "<ns0:manifest>\n"
            '<ns0:item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>\n'
            "</ns0:manifest>\n"
            '<ns0:spine toc="ncx">\n'
            '<ns0:itemref idref="ch1"/>\n'
            "</ns0:spine>\n"
            "</ns0:package>\n"
        )
        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        CompatProcessor().fix(epub, [], {"normalise": True})

        result = opf_path.read_text()
        assert 'idref="ch1"' in result
        assert 'href="ch1.xhtml"' in result

    def test_handles_corrupt_opf(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = extract_dir / "content.opf"
        opf_path.write_text("not xml <<<")
        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        fixes = CompatProcessor().fix(epub, [], {"normalise": True})
        assert isinstance(fixes, list)

    def test_normalise_opf_preserves_non_opf_namespaced_attrs(self, tmp_path: Path) -> None:
        """Elements with both OPF-namespaced attributes and
        non-OPF-namespaced attributes — OPF attrs are stripped,
        non-OPF attrs are kept."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ns0:package xmlns:ns0="http://www.idpf.org/2007/opf"'
            ' xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">'
            "<ns0:manifest>"
            '<ns0:item ns0:id="ch1" dc:title="Chapter One"'
            ' href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            "</ns0:manifest>"
            "</ns0:package>"
        )
        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        CompatProcessor().fix(epub, [], {"normalise": True})

        result = opf_path.read_text()
        # OPF-namespaced attributes should be bare
        assert "ns0:id" not in result
        assert 'id="ch1"' in result
        # Non-OPF namespace prefix should be preserved
        assert "dc:title" in result


class TestCompatCleanupCss:
    """Test suite for CSS @font-face cleanup."""

    def test_removes_font_face_for_stripped_font(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        css_file = extract_dir / "style.css"
        css_file.write_text(
            '@font-face {\n  font-family: "Body";\n  src: url("fonts/body.otf");\n}\np { margin: 0; }\n'
        )
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="css" href="style.css" media-type="text/css"/>'
            "</manifest></package>"
        )

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="font: fonts/body.otf",
                description="Embedded font found: fonts/body.otf",
                fix_possible=True,
            )
        ]
        CompatProcessor().fix(epub, issues, {"normalise": True})

        result = css_file.read_text()
        assert "@font-face" not in result
        assert "p { margin: 0; }" in result

    def test_preserves_unrelated_font_face(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        css_file = extract_dir / "style.css"
        css_file.write_text('@font-face {\n  font-family: "Title";\n  src: url("fonts/title.woff2");\n}\n')
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="css" href="style.css" media-type="text/css"/>'
            "</manifest></package>"
        )

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="font: fonts/body.otf",
                description="Embedded font found: fonts/body.otf",
                fix_possible=True,
            )
        ]
        CompatProcessor().fix(epub, issues, {"normalise": True})

        result = css_file.read_text()
        assert "@font-face" in result

    def test_strip_font_faces_skips_unreadable_css(self, tmp_path: Path) -> None:
        """When a CSS file cannot be read (invalid encoding), it should be
        silently skipped without crashing."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        css_file = extract_dir / "style.css"
        css_file.write_bytes(b"\x80\x81\x82")  # invalid UTF-8
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="css" href="style.css" media-type="text/css"/>'
            "</manifest></package>"
        )

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="font: fonts/body.otf",
                description="Embedded font found: fonts/body.otf",
                fix_possible=True,
            )
        ]
        # Should not raise
        CompatProcessor().fix(epub, issues, {"normalise": True})
