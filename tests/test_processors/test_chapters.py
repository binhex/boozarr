"""Tests for ChaptersProcessor."""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.epub import EpubWrapper
from boozarr.processors.chapters import ChaptersProcessor

_SAMPLE_NCX = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="x"/></head>
  <navMap>
    <navPoint id="c1" playOrder="1"><navLabel><text>Ch1</text></navLabel><content src="ch1.xhtml"/></navPoint>
  </navMap>
</ncx>"""


class TestChaptersCheck:
    def test_no_issues_when_toc_populated(self) -> None:
        epub = MagicMock()
        epub.read_file.side_effect = lambda p: {"toc.ncx": _SAMPLE_NCX, "content.opf": "<package/>"}[p]
        epub.get_opf_path.return_value = "content.opf"
        issues = ChaptersProcessor().check(epub)
        assert issues == []

    def test_issue_when_toc_empty(self) -> None:
        epub = MagicMock()
        epub.read_file.side_effect = lambda p: {"toc.ncx": "<ncx><navMap/></ncx>", "content.opf": "<package/>"}[p]
        epub.get_opf_path.return_value = "content.opf"
        issues = ChaptersProcessor().check(epub)
        assert len(issues) == 1
        assert issues[0].processor == "chapters"
        assert issues[0].fix_possible is True

    def test_issue_when_ncx_missing(self) -> None:
        epub = MagicMock()
        epub.read_file.side_effect = FileNotFoundError("no file")
        epub.get_opf_path.return_value = "content.opf"
        issues = ChaptersProcessor().check(epub)
        assert len(issues) == 1

    def test_issue_when_ncx_read_fails(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf_with_ncx = '<package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>T</dc:title></metadata><manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest></package>'
        epub.read_file.side_effect = [opf_with_ncx, RuntimeError("NCX read failure")]
        issues = ChaptersProcessor().check(epub)
        assert len(issues) == 1
        assert issues[0].processor == "chapters"

    def test_issue_when_ncx_xml_unparseable(self) -> None:
        """check() returns 1 issue when NCX content is not valid XML."""
        epub = MagicMock()
        epub.read_file.side_effect = lambda p: {
            "toc.ncx": "not valid xml <<<",
            "content.opf": "<package/>",
        }[p]
        epub.get_opf_path.return_value = "content.opf"
        issues = ChaptersProcessor().check(epub)
        assert len(issues) == 1
        assert issues[0].processor == "chapters"


class TestChaptersFix:
    def test_fix_returns_empty_when_not_extracted(self) -> None:
        epub = MagicMock()
        epub._extract_dir = None
        fixes = ChaptersProcessor().fix(epub, [MagicMock()], {})
        assert fixes == []


class TestChaptersFixIntegration:
    """Integration tests for chapters fix() writing real NCX files."""

    def test_fix_creates_ncx_from_h2_headings(self, tmp_path: Path) -> None:
        """fix() should use h1/h2 fallback when no Chapter pattern matches."""
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "content.opf",
                '<?xml version="1.0" encoding="UTF-8"?><package><metadata><dc:title>Test</dc:title></metadata></package>',
            )
            # XHTML with <h2> heading but no "Chapter" pattern
            zf.writestr("OEBPS/section1.xhtml", "<html><body><h2>Introduction</h2><p>Text</p></body></html>")
            zf.writestr("OEBPS/section2.xhtml", "<html><body><h2>The Beginning</h2><p>Text</p></body></html>")

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = ChaptersProcessor()
        issues = processor.check(wrapper)
        assert len(issues) == 1  # no NCX at all

        fixes = processor.fix(wrapper, issues, {})
        assert len(fixes) >= 1

        wrapper.repack(epub_path)
        wrapper2 = EpubWrapper(epub_path)
        issues_after = processor.check(wrapper2)
        assert len(issues_after) == 0


class TestChaptersProcessorIntegration:
    """Integration tests using real EpubWrapper and real EPUB files."""

    _NCX_WITH_CHAPTERS = _SAMPLE_NCX

    _OPF_WITH_NCX = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns:dc="http://purl.org/dc/elements/1.1/">
  <metadata><dc:title>Test</dc:title></metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="ch1"/>
  </spine>
</package>"""

    def _make_epub_with_ncx(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr("content.opf", self._OPF_WITH_NCX)
            zf.writestr("toc.ncx", self._NCX_WITH_CHAPTERS)
            zf.writestr("ch1.xhtml", "<html><body><h1>Chapter 1</h1><p>Text</p></body></html>")

    def _make_epub_without_ncx(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr("content.opf", self._OPF_WITH_NCX)
            zf.writestr("ch1.xhtml", "<html><body><h1>Chapter 1</h1><p>Text</p></body></html>")

    def test_check_returns_zero_when_ncx_has_chapters(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_ncx(epub_path)
        wrapper = EpubWrapper(epub_path)
        issues = ChaptersProcessor().check(wrapper)
        assert len(issues) == 0, f"Expected 0 issues (NCX has navPoints), got {len(issues)}"

    def test_check_returns_one_when_ncx_missing(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_without_ncx(epub_path)
        wrapper = EpubWrapper(epub_path)
        issues = ChaptersProcessor().check(wrapper)
        assert len(issues) == 1

    def test_fix_creates_ncx_content(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_without_ncx(epub_path)

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = ChaptersProcessor()
        issues = processor.check(wrapper)
        assert len(issues) == 1

        fixes = processor.fix(wrapper, issues, {})
        assert len(fixes) > 0

        wrapper.repack(epub_path)

        with zipfile.ZipFile(epub_path, "r") as zf:
            names = zf.namelist()
            ncx_files = [n for n in names if n.endswith(".ncx")]
            assert len(ncx_files) > 0
            ncx_content = zf.read(ncx_files[0]).decode()
            assert "navPoint" in ncx_content

        wrapper2 = EpubWrapper(epub_path)
        issues_after = processor.check(wrapper2)
        assert len(issues_after) == 0, f"Expected 0 issues after fix, got {len(issues_after)}"

    def test_check_finds_ncx_in_subdirectory(self, tmp_path: Path) -> None:
        """check() should resolve NCX href relative to the OPF directory.

        When the OPF lives in OEBPS/ and the NCX href is "toc.ncx", the
        actual NCX path is OEBPS/toc.ncx, not toc.ncx at the EPUB root.
        """
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" '
                'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                'media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "OEBPS/content.opf",
                '<?xml version="1.0"?><package>'
                "<manifest>"
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
                "</manifest></package>",
            )
            zf.writestr(
                "OEBPS/toc.ncx",
                '<?xml version="1.0"?>'
                '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
                '<navMap><navPoint id="c1" playOrder="1">'
                "<navLabel><text>Ch1</text></navLabel>"
                '<content src="ch1.xhtml"/>'
                "</navPoint></navMap></ncx>",
            )
        wrapper = EpubWrapper(epub_path)
        issues = ChaptersProcessor().check(wrapper)
        assert len(issues) == 0, f"NCX in OEBPS/ with navPoints should report 0 issues, got {len(issues)}"

    def test_check_returns_one_when_ncx_is_empty(self, tmp_path: Path) -> None:
        """An EPUB with an empty NCX (no navPoints) should report 1 issue."""
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "content.opf",
                '<?xml version="1.0"?><package><manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest></package>',
            )
            zf.writestr(
                "toc.ncx",
                '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap></navMap></ncx>',
            )
        wrapper = EpubWrapper(epub_path)
        issues = ChaptersProcessor().check(wrapper)
        assert len(issues) == 1

    def test_fix_writes_to_existing_ncx(self, tmp_path: Path) -> None:
        """fix() discovers the existing NCX via rglob and writes to it."""
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" '
                'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                'media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "OEBPS/content.opf",
                '<?xml version="1.0"?><package>'
                "<manifest>"
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
                "</manifest></package>",
            )
            zf.writestr(
                "OEBPS/toc.ncx",
                '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap></navMap></ncx>',
            )
            zf.writestr("OEBPS/ch1.xhtml", "<html><body><h1>Chapter 1</h1></body></html>")

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = ChaptersProcessor()
        issues = processor.check(wrapper)
        assert len(issues) == 1

        fixes = processor.fix(wrapper, issues, {})
        assert len(fixes) == 1
        # Fix should reference the existing NCX path, not the default "toc.ncx"
        assert "OEBPS/toc.ncx" in fixes[0].location

    def test_ncx_found_by_extension_not_mediatype(self, tmp_path: Path) -> None:
        """_search_opf_for_ncx finds NCX by .ncx extension when media-type
        doesn't contain 'ncx' or 'dtbncx'."""
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" '
                'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="content.opf" '
                'media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "content.opf",
                '<?xml version="1.0"?><package>'
                "<manifest>"
                '<item id="ncx" href="toc.ncx" media-type="text/xml"/>'
                "</manifest></package>",
            )
            zf.writestr(
                "toc.ncx",
                '<?xml version="1.0"?>'
                '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
                '<navMap><navPoint id="c1" playOrder="1">'
                "<navLabel><text>Ch1</text></navLabel>"
                '<content src="ch1.xhtml"/>'
                "</navPoint></navMap></ncx>",
            )
        wrapper = EpubWrapper(epub_path)
        issues = ChaptersProcessor().check(wrapper)
        assert len(issues) == 0, f"NCX found by .ncx extension should report 0 issues, got {len(issues)}"
