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


class TestFixSpineFallbackIntegration:
    """Integration tests for spine fallback in fix()."""

    def test_fix_uses_spine_fallback_for_no_marker_epub(self, tmp_path: Path) -> None:
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
                '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>'
                "</manifest>"
                '<spine><itemref idref="ch1"/><itemref idref="ch2"/></spine></package>',
            )
            zf.writestr("chapter1.xhtml", "<html><body><p>Text.</p></body></html>" * 50)
            zf.writestr("chapter2.xhtml", "<html><body><p>More text.</p></body></html>" * 50)

        from boozarr.epub import EpubWrapper

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        processor = ChaptersProcessor()
        issues = processor.check(wrapper)
        assert len(issues) == 1
        fixes = processor.fix(wrapper, issues, {})
        assert len(fixes) == 1

    def test_fix_has_chapters_after_repack(self, tmp_path: Path) -> None:
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
                '<item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
                "</manifest>"
                '<spine><itemref idref="ch"/></spine></package>',
            )
            zf.writestr("chapter.xhtml", "<html><body><p>Once upon a time...</p></body></html>" * 50)

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        processor = ChaptersProcessor()
        issues = processor.check(wrapper)
        assert len(issues) == 1
        fixes = processor.fix(wrapper, issues, {})
        assert len(fixes) == 1
        wrapper.repack(epub_path)
        wrapper2 = EpubWrapper(epub_path)
        issues_after = processor.check(wrapper2)
        assert len(issues_after) == 0


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


class TestLabelFromFilename:
    """Tests for _label_from_filename static method."""

    def test_extracts_trailing_digits(self) -> None:
        assert ChaptersProcessor._label_from_filename("chapter_3") == "Chapter 3"
        assert ChaptersProcessor._label_from_filename("ch01") == "Chapter 1"
        assert ChaptersProcessor._label_from_filename("part0007") == "Chapter 7"

    def test_strips_leading_zeros(self) -> None:
        assert ChaptersProcessor._label_from_filename("split_005") == "Chapter 5"
        assert ChaptersProcessor._label_from_filename("temp_calibre_txt_input_to_html_split_001") == "Chapter 1"

    def test_mixed_digits_uses_trailing(self) -> None:
        assert ChaptersProcessor._label_from_filename("05_c1") == "Chapter 1"
        assert ChaptersProcessor._label_from_filename("book2_chapter_10") == "Chapter 10"

    def test_no_digits_uses_stem(self) -> None:
        assert ChaptersProcessor._label_from_filename("titlepage") == "Titlepage"
        assert ChaptersProcessor._label_from_filename("story") == "Story"

    def test_underscores_replaced_with_spaces(self) -> None:
        assert ChaptersProcessor._label_from_filename("index_split_000") == "Chapter 0"


class TestResolveSpineOrder:
    """Tests for _resolve_spine_order static method."""

    def test_returns_spine_order_map(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        (extract_dir / "OEBPS").mkdir(parents=True)
        opf_path = "OEBPS/content.opf"
        opf_content = (
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf">'
            "<manifest>"
            '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>'
            "</manifest>"
            "<spine>"
            '<itemref idref="cover"/>'
            '<itemref idref="ch1"/>'
            '<itemref idref="ch2"/>'
            "</spine>"
            "</package>"
        )
        (extract_dir / opf_path).write_text(opf_content)
        (extract_dir / "OEBPS/chapter1.xhtml").write_text("<html/>")
        (extract_dir / "OEBPS/chapter2.xhtml").write_text("<html/>")
        (extract_dir / "OEBPS/cover.xhtml").write_text("<html/>")

        order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)
        assert order == {
            "OEBPS/cover.xhtml": 0,
            "OEBPS/chapter1.xhtml": 1,
            "OEBPS/chapter2.xhtml": 2,
        }

    def test_handles_root_opf_path(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest><item id="ch" href="ch.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="ch"/></spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)
        (extract_dir / "ch.xhtml").write_text("<html/>")
        order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)
        assert order == {"ch.xhtml": 0}

    def test_skips_missing_idref(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest><item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>'
            "<spine>"
            '<itemref idref="missing"/>'
            '<itemref idref="ch1"/>'
            "</spine></package>"
        )
        (extract_dir / opf_path).write_text(opf_content)
        order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)
        assert order == {"ch1.xhtml": 0}

    def test_returns_empty_on_corrupt_xml(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        (extract_dir / opf_path).write_text("not valid xml <<<")
        order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)
        assert order == {}


class TestDiscoverFromSpine:
    """Tests for _discover_from_spine static method."""

    def test_discovers_from_spine_items(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        (extract_dir / "OEBPS").mkdir(parents=True)
        opf_path = "OEBPS/content.opf"
        opf_content = (
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf">'
            "<manifest>"
            '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ch3" href="chapter3.xhtml" media-type="application/xhtml+xml"/>'
            "</manifest>"
            "<spine>"
            '<itemref idref="ch1"/>'
            '<itemref idref="ch2"/>'
            '<itemref idref="ch3"/>'
            "</spine></package>"
        )
        (extract_dir / opf_path).write_text(opf_content)
        (extract_dir / "OEBPS/chapter1.xhtml").write_text("<html><body>" + "x" * 3000 + "</body></html>")
        (extract_dir / "OEBPS/chapter2.xhtml").write_text("<html><body>" + "x" * 3000 + "</body></html>")
        (extract_dir / "OEBPS/chapter3.xhtml").write_text("<html><body>" + "x" * 3000 + "</body></html>")

        discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)
        assert len(discovered) == 3
        assert discovered[0] == ("OEBPS/chapter1.xhtml", "Chapter 1")
        assert discovered[1] == ("OEBPS/chapter2.xhtml", "Chapter 2")

    def test_filters_non_content_files(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="title" href="title_page.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
            "</manifest>"
            "<spine>"
            '<itemref idref="cover"/>'
            '<itemref idref="title"/>'
            '<itemref idref="ch1"/>'
            "</spine></package>"
        )
        (extract_dir / opf_path).write_text(opf_content)
        for name in ["cover.xhtml", "title_page.xhtml", "chapter1.xhtml"]:
            (extract_dir / name).write_text("<html><body>" + "x" * 3000 + "</body></html>")

        discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)
        assert len(discovered) == 1
        assert discovered[0][0] == "chapter1.xhtml"

    def test_filters_small_files(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="tiny" href="tiny.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="big" href="big.xhtml" media-type="application/xhtml+xml"/>'
            "</manifest>"
            '<spine><itemref idref="tiny"/><itemref idref="big"/></spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)
        (extract_dir / "tiny.xhtml").write_text("small")
        (extract_dir / "big.xhtml").write_text("x" * 3000)

        discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)
        assert len(discovered) == 1
        assert discovered[0][0] == "big.xhtml"

    def test_returns_empty_on_spine_parse_failure(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        (extract_dir / opf_path).write_text("<<<garbage>>>")
        discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)
        assert discovered == []

    def test_skips_missing_spine_file(self, tmp_path: Path) -> None:
        """Spine references a file not present in extract_dir — skip it."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="missing" href="ghost.xhtml" media-type="application/xhtml+xml"/>'
            "</manifest>"
            '<spine><itemref idref="ch1"/><itemref idref="missing"/></spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)
        (extract_dir / "ch1.xhtml").write_text("x" * 3000)
        # ghost.xhtml NOT created — should be skipped

        discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)
        assert len(discovered) == 1
        assert discovered[0][0] == "ch1.xhtml"


class TestDiscoverChaptersMultiMatch:
    """Tests for the multi-match rewrite of _discover_chapters."""

    def test_finds_all_chapter_markers_in_file(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapters.xhtml"
        content = "<html><body>"
        for i in range(1, 11):
            content += f"<p>CHAPTER {i}</p>\n"
        content += "</body></html>"
        xhtml.write_text(content)
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest><item id="ch" href="chapters.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="ch"/></spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)
        discovered = ChaptersProcessor._discover_chapters(extract_dir, opf_path)
        assert len(discovered) == 10
        assert discovered[0][1] == "CHAPTER 1"
        assert discovered[9][1] == "CHAPTER 10"

    def test_finds_mixed_patterns_in_file(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "book.xhtml"
        content = "<html><body><p>Part 1</p><p>Chapter 1</p><p>Chapter 2</p><p>Section 1</p></body></html>"
        xhtml.write_text(content)
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        labels = [m[1] for m in discovered]
        assert "Part 1" in labels
        assert "Chapter 1" in labels
        assert "Chapter 2" in labels
        assert "Section 1" in labels

    def test_dedup_overlapping_patterns(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapters.xhtml"
        xhtml.write_text("<html><body><p>CHAPTER 1</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        assert len(discovered) == 1

    def test_h1_fallback_when_no_pattern_matches(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "story.xhtml"
        xhtml.write_text("<html><body><h1>The Journey Begins</h1><p>Text</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        assert len(discovered) == 1
        assert discovered[0][1] == "The Journey Begins"

    def test_no_h1_fallback_when_pattern_already_matched(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapter.xhtml"
        xhtml.write_text("<html><body><h1>Book Title</h1><p>Chapter 1</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        labels = [m[1] for m in discovered]
        assert "Chapter 1" in labels
        assert "Book Title" not in labels

    def test_returns_empty_when_no_markers_and_no_headings(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "blank.xhtml"
        xhtml.write_text("<html><body><p>Just some text.</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        assert discovered == []

    def test_skips_unreadable_xhtml_file(self, tmp_path: Path) -> None:
        """When read_text() raises, the file is silently skipped."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        bad_file = extract_dir / "bad.xhtml"
        bad_file.write_bytes(b"\x80\x81\x82")  # invalid UTF-8

        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        # No matches (bad file skipped), so result is empty
        assert discovered == []

    def test_sorts_by_spine_order_when_opf_available(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml1 = extract_dir / "middle.xhtml"
        xhtml1.write_text("<html><body><h2>Chapter 1</h2></body></html>")
        xhtml2 = extract_dir / "first.xhtml"
        xhtml2.write_text("<html><body><h2>Prologue</h2></body></html>")
        xhtml3 = extract_dir / "last.xhtml"
        xhtml3.write_text("<html><body><h2>Epilogue</h2></body></html>")
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            "<manifest>"
            '<item id="f" href="first.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="m" href="middle.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="l" href="last.xhtml" media-type="application/xhtml+xml"/>'
            "</manifest>"
            "<spine>"
            '<itemref idref="f"/><itemref idref="m"/><itemref idref="l"/>'
            "</spine></package>"
        )
        (extract_dir / opf_path).write_text(opf_content)
        discovered = ChaptersProcessor._discover_chapters(extract_dir, opf_path)
        assert discovered[0][1] == "Prologue"
        assert discovered[1][1] == "Chapter 1"
        assert discovered[2][1] == "Epilogue"


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

    def test_search_opf_finds_ncx_by_extension(self) -> None:
        """_search_opf_for_ncx finds NCX when href ends with .ncx but media-type
        is not dtbncx or ncx (hits the extension-fallback branch L71)."""
        from unittest.mock import MagicMock

        epub = MagicMock()
        opf = '<package><manifest><item id="ncx" href="toc.ncx" media-type="text/xml"/></manifest></package>'
        epub.read_file.return_value = opf
        result = ChaptersProcessor._search_opf_for_ncx(epub, "content.opf")
        assert result == "toc.ncx"


class TestFixEdgeCases:
    def test_fix_handles_get_opf_path_raising(self, tmp_path: Path) -> None:
        """fix() survives epub.get_opf_path() raising an exception."""
        from unittest.mock import MagicMock

        epub = MagicMock()
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        epub._extract_dir = extract_dir
        epub.get_opf_path.side_effect = RuntimeError("OPF not found")

        (extract_dir / "ch.xhtml").write_text("<html><body><h1>Chapter</h1></body></html>")

        processor = ChaptersProcessor()
        fixes = processor.fix(epub, [MagicMock()], {})
        assert len(fixes) >= 1
