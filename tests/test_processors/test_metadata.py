"""Tests for MetadataProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.metadata import MetadataProcessor


class TestMetadataCheck:
    def test_no_issues_when_all_present(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {"dc:title": "T", "dc:creator": "A", "dc:language": "en", "dc:date": "2024"}
        assert MetadataProcessor().check(epub) == []

    def test_issues_for_missing_fields(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {}
        issues = MetadataProcessor().check(epub)
        assert len(issues) == 4


class TestMetadataFix:
    def _make_issue(self, field: str) -> MagicMock:
        return MagicMock(
            location=f"content.opf <metadata> {field}",
            description=f"Missing {field}",
            processor="metadata",
        )

    def test_fix_infers_title(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {}
        epub.path = "/lib/Isaac Asimov - Foundation.epub"
        fixes = MetadataProcessor().fix(epub, [self._make_issue("dc:title")], {})
        assert len(fixes) == 1
        assert "Foundation" in fixes[0].new_value

    def test_fix_infers_creator(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {}
        epub.path = "/lib/Isaac Asimov - Foundation.epub"
        fixes = MetadataProcessor().fix(epub, [self._make_issue("dc:creator")], {})
        assert len(fixes) == 1
        assert "Asimov" in fixes[0].new_value

    def test_fix_defaults_language(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {}
        epub.path = "/lib/book.epub"
        fixes = MetadataProcessor().fix(epub, [self._make_issue("dc:language")], {})
        assert len(fixes) == 1
        assert fixes[0].new_value == "en"

    def test_fix_defaults_date(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {}
        epub.path = "/lib/book.epub"
        fixes = MetadataProcessor().fix(epub, [self._make_issue("dc:date")], {})
        assert len(fixes) == 1
        assert fixes[0].new_value == "2026-01-01"

    def test_fix_multiple_missing_fields(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {}
        epub.path = "/lib/Author - Title.epub"
        fields = ["dc:title", "dc:creator", "dc:language", "dc:date"]
        issues = [self._make_issue(f) for f in fields]
        fixes = MetadataProcessor().fix(epub, issues, {})  # type: ignore[arg-type]
        assert len(fixes) == 4

    def test_fix_no_filename_match_without_dash(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {}
        epub.path = "/lib/unknown.epub"
        fixes = MetadataProcessor().fix(epub, [self._make_issue("dc:title")], {})
        assert len(fixes) == 1
        assert fixes[0].new_value == "unknown"
