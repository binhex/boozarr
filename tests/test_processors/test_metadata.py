"""Tests for MetadataProcessor."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from boozarr.epub import EpubWrapper
from boozarr.processors.metadata import MetadataProcessor

_EMPTY_OPF = '<?xml version="1.0" encoding="UTF-8"?><package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata></metadata></package>'
_FULL_OPF = '<?xml version="1.0" encoding="UTF-8"?><package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>T</dc:title><dc:creator>A</dc:creator><dc:language>en</dc:language><dc:date>2024</dc:date></metadata></package>'


class TestMetadataCheck:
    def test_no_issues_when_all_present(self) -> None:
        epub = MagicMock(spec=["read_file"])
        epub.read_file.return_value = _FULL_OPF
        assert MetadataProcessor().check(epub) == []

    def test_issues_for_missing_fields(self) -> None:
        epub = MagicMock(spec=["read_file"])
        epub.read_file.return_value = _EMPTY_OPF
        issues = MetadataProcessor().check(epub)
        assert len(issues) == 4

    def test_error_when_opf_unreadable(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        epub.read_file.side_effect = PermissionError("No access")
        issues = MetadataProcessor().check(epub)
        assert len(issues) == 1
        assert issues[0].processor == "metadata"
        assert "Cannot read" in issues[0].description


class TestMetadataFix:
    def _make_issue(self, field: str) -> MagicMock:
        return MagicMock(
            location="OEBPS/content.opf",
            description=f"Missing {field}",
            processor="metadata",
        )

    def _make_extracted_epub(self, tmp_path: Path) -> tuple[EpubWrapper, Path]:
        """Create a real EPUB with empty metadata, extract it, return (wrapper, extract_dir)."""
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
            )
            zf.writestr("OEBPS/content.opf", _EMPTY_OPF)
            zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Test</p></body></html>")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        return wrapper, extract_dir

    def test_fix_infers_title(self, tmp_path: Path) -> None:
        wrapper, _ = self._make_extracted_epub(tmp_path)
        wrapper.path = Path("/lib/Isaac Asimov - Foundation.epub")
        fixes = MetadataProcessor().fix(wrapper, [self._make_issue("dc:title")], {})
        assert len(fixes) >= 1
        descs = " ".join(f.description for f in fixes)
        assert "Foundation" in descs

    def test_fix_infers_creator(self, tmp_path: Path) -> None:
        wrapper, _ = self._make_extracted_epub(tmp_path)
        wrapper.path = Path("/lib/Isaac Asimov - Foundation.epub")
        fixes = MetadataProcessor().fix(wrapper, [self._make_issue("dc:creator")], {})
        assert len(fixes) >= 1
        descs = " ".join(f.description for f in fixes)
        assert "Asimov" in descs

    def test_fix_defaults_language(self, tmp_path: Path) -> None:
        wrapper, _ = self._make_extracted_epub(tmp_path)
        wrapper.path = Path("/lib/book.epub")
        fixes = MetadataProcessor().fix(wrapper, [self._make_issue("dc:language")], {})
        assert len(fixes) >= 1
        descs = " ".join(f.description for f in fixes)
        assert "en" in descs

    def test_fix_defaults_date(self, tmp_path: Path) -> None:
        wrapper, _ = self._make_extracted_epub(tmp_path)
        wrapper.path = Path("/lib/book.epub")
        fixes = MetadataProcessor().fix(wrapper, [self._make_issue("dc:date")], {})
        assert len(fixes) >= 1
        assert any("date" in f.description.lower() for f in fixes)

    def test_fix_multiple_missing_fields(self, tmp_path: Path) -> None:
        wrapper, _ = self._make_extracted_epub(tmp_path)
        wrapper.path = Path("/lib/Author - Title.epub")
        fields = ["dc:title", "dc:creator", "dc:language", "dc:date"]
        issues = [self._make_issue(f) for f in fields]
        fixes = MetadataProcessor().fix(wrapper, issues, {})  # type: ignore[arg-type]
        assert len(fixes) == 4

    def test_fix_no_filename_match_without_dash(self, tmp_path: Path) -> None:
        wrapper, _ = self._make_extracted_epub(tmp_path)
        wrapper.path = Path("/lib/unknown.epub")
        fixes = MetadataProcessor().fix(wrapper, [self._make_issue("dc:title")], {})
        assert len(fixes) >= 1
        descs = " ".join(f.description for f in fixes)
        assert "unknown" in descs

    def test_fix_without_extract_returns_empty(self) -> None:
        epub = MagicMock()
        epub.path = Path("/lib/test.epub")
        fixes = MetadataProcessor().fix(
            epub, [MagicMock(location="opf", description="Missing dc:title", processor="metadata")], {}
        )
        assert fixes == []


class TestMetadataProcessorIntegration:
    """Integration tests that verify metadata fixes persist to disk."""

    def _make_epub_with_empty_metadata(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
            )
            zf.writestr("OEBPS/content.opf", _EMPTY_OPF)
            zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Test</p></body></html>")

    def _read_opf_metadata(self, epub_path: Path) -> str:
        with zipfile.ZipFile(epub_path, "r") as zf:
            return zf.read("OEBPS/content.opf").decode()

    def _make_issue(self, field: str) -> MagicMock:
        return MagicMock(
            location="OEBPS/content.opf",
            description=f"Missing {field}",
            processor="metadata",
        )

    def test_fix_actually_writes_opf_metadata(self, tmp_path: Path) -> None:
        """After fix() + repack, the EPUB's OPF should contain the inferred metadata."""
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_empty_metadata(epub_path)

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = MetadataProcessor()
        issues = processor.check(wrapper)
        assert len(issues) == 4

        fields = ["dc:title", "dc:creator", "dc:language", "dc:date"]
        issues_list = [self._make_issue(f) for f in fields]
        processor.fix(wrapper, issues_list, {})  # type: ignore[arg-type]

        # Repack so changes are written to the EPUB
        wrapper.repack(epub_path)

        opf_after = self._read_opf_metadata(epub_path)
        assert "dc:title" in opf_after
        assert "dc:creator" in opf_after
        assert "dc:language" in opf_after

    def test_check_returns_zero_after_fix_and_repack(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "book.epub"
        self._make_epub_with_empty_metadata(epub_path)

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = MetadataProcessor()
        assert len(processor.check(wrapper)) == 4

        fields = ["dc:title", "dc:creator", "dc:language", "dc:date"]
        processor.fix(wrapper, [self._make_issue(f) for f in fields], {})

        wrapper.repack(epub_path)

        wrapper2 = EpubWrapper(epub_path)
        issues_after = processor.check(wrapper2)
        assert len(issues_after) == 0, f"Expected 0 issues after fix+repack, got {len(issues_after)}"

    def test_check_handles_nonstandard_opf_path(self, tmp_path: Path) -> None:
        """MetadataProcessor should find the OPF even when it's not at OEBPS/content.opf."""
        epub_path = tmp_path / "book.epub"
        # OPF at root level (content.opf) with container.xml pointing to it
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "content.opf",
                '<?xml version="1.0" encoding="UTF-8"?><package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata></metadata></package>',
            )
            zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Test</p></body></html>")

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = MetadataProcessor()
        issues = processor.check(wrapper)
        assert len(issues) == 4, f"Expected 4 metadata issues (OPF at non-standard path), got {len(issues)}: {issues}"

    def test_fix_works_with_nonstandard_opf_path(self, tmp_path: Path) -> None:
        """MetadataProcessor should fix metadata even when OPF is at a non-standard path."""
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "content.opf",
                '<?xml version="1.0" encoding="UTF-8"?><package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata></metadata></package>',
            )
            zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Test</p></body></html>")

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = MetadataProcessor()
        # Check finds 4 issues
        assert len(processor.check(wrapper)) == 4

        # Fix should work
        fields = ["dc:title", "dc:creator", "dc:language", "dc:date"]
        fixes = processor.fix(
            wrapper, [MagicMock(location="test", description=f"Missing {f}", processor="metadata") for f in fields], {}
        )
        assert len(fixes) == 4, f"Expected 4 fixes, got {len(fixes)}"

        # Repack and re-check
        wrapper.repack(epub_path)
        wrapper2 = EpubWrapper(epub_path)
        issues_after = processor.check(wrapper2)
        assert len(issues_after) == 0, f"Expected 0 issues after fix, got {len(issues_after)}"
