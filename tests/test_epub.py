"""Tests for EpubWrapper — EPUB file validation, extract, repack."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from boozarr.epub import EpubWrapper


class TestEpubWrapperInit:
    def test_init_computes_sha256(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_bytes(b"fake epub content")
        wrapper = EpubWrapper(epub_path)
        expected = hashlib.sha256(b"fake epub content").hexdigest()
        assert wrapper.file_hash == expected
        assert wrapper.path == epub_path

    def test_init_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            EpubWrapper(Path("/nonexistent.epub"))


class TestEpubWrapperValidation:
    def test_validate_valid_zip(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "valid.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
        EpubWrapper(epub_path).validate()

    def test_validate_not_a_zip(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "notazip.epub"
        epub_path.write_bytes(b"plain data")
        with pytest.raises(zipfile.BadZipFile):
            EpubWrapper(epub_path).validate()

    def test_validate_missing_opf(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "noopf.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
        with pytest.raises(ValueError, match="Missing EPUB structure"):
            EpubWrapper(epub_path).validate()


class TestEpubWrapperRepack:
    def test_extract_and_repack_round_trip(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "input.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr("OEBPS/chapter1.xhtml", "<html><body><p>Hello</p></body></html>")

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        fpath = extract_dir / "OEBPS/chapter1.xhtml"
        assert fpath.read_text() == "<html><body><p>Hello</p></body></html>"

        wrapper.write_file(fpath, "<html><body><p>Modified</p></body></html>")

        output = tmp_path / "output.epub"
        wrapper.repack(output)
        with zipfile.ZipFile(output, "r") as zf:
            assert zf.read("OEBPS/chapter1.xhtml").decode() == "<html><body><p>Modified</p></body></html>"

    def test_repack_without_extract_raises(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "a.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
        wrapper = EpubWrapper(epub_path)
        with pytest.raises(RuntimeError, match="No extracted directory"):
            wrapper.repack(tmp_path / "out.epub")
