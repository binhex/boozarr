"""Tests for CompressionProcessor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from boozarr.processors.compression import CompressionProcessor


class TestCompressionCheck:
    def test_no_issues_when_clean(self) -> None:
        epub = MagicMock()
        epub.extra_files = [Path("OEBPS/content.opf")]
        assert CompressionProcessor().check(epub) == []

    def test_issue_when_ds_store_present_with_compress_configured(self) -> None:
        epub = MagicMock()
        epub.extra_files = [Path(".DS_Store"), Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub, {"compress": 9})
        # 1 extraneous + 1 compression = 2 issues
        assert len(issues) == 2
        assert any("extraneous" in i.description for i in issues)
        assert any("compression" in i.description.lower() for i in issues)

    def test_no_issues_when_compress_not_configured(self) -> None:
        epub = MagicMock()
        epub.extra_files = [Path(".DS_Store"), Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub, {})
        assert len(issues) == 0

    def test_no_issues_when_config_is_none(self) -> None:
        epub = MagicMock()
        epub.extra_files = [Path(".DS_Store"), Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub, None)
        assert len(issues) == 0

    def test_no_issues_when_no_config_passed(self) -> None:
        """Check with no config argument returns empty (no-op)."""
        epub = MagicMock()
        epub.extra_files = [Path(".DS_Store"), Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub)
        assert len(issues) == 0

    def test_issues_when_compress_configured(self) -> None:
        epub = MagicMock()
        epub.extra_files = [Path(".DS_Store"), Path("thumbs.db")]
        issues = CompressionProcessor().check(epub, {"compress": 9})
        # 1 extraneous (reporting 2 files) + 1 compression = 2 issues
        assert len(issues) == 2
        assert any("2 extraneous" in i.description for i in issues)
        assert any("compression" in i.description.lower() for i in issues)

    def test_sets_compress_level_even_when_clean(self) -> None:
        """check() must set _compress_level and report compression as an issue."""
        epub = MagicMock()
        epub.extra_files = [Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub, {"compress": 7})
        assert len(issues) == 1, "compression should be reported as an issue when configured"
        assert "compression" in issues[0].description.lower()
        assert epub._compress_level == 7

    def test_compress_creates_issue_when_configured(self) -> None:
        """When compress is configured, check() returns an issue even with no extraneous files."""
        epub = MagicMock()
        epub.extra_files = [Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub, {"compress": 9})
        assert len(issues) == 1
        assert "compression" in issues[0].description.lower()
        assert issues[0].fix_possible is True


class TestCompressionFix:
    def test_fix_cleans_extraneous(self) -> None:
        epub = MagicMock()
        issue = MagicMock(
            location="archive root",
            description="Found 1 extraneous file(s)",
        )
        fixes = CompressionProcessor().fix(epub, [issue], {"compress": 9})
        assert len(fixes) == 1
        assert "cleaned" in fixes[0].new_value
        assert epub._compress_level == 9

    def test_fix_sets_compress_level(self) -> None:
        epub = MagicMock()
        fixes = CompressionProcessor().fix(epub, [], {"compress": 7})
        assert len(fixes) == 0
        assert epub._compress_level == 7

    def test_fix_without_issues_still_sets_compress_level(self) -> None:
        epub = MagicMock()
        fixes = CompressionProcessor().fix(epub, [], {"compress": 5})
        assert len(fixes) == 0
        assert epub._compress_level == 5

    def test_fix_reports_compression_level(self) -> None:
        """fix() should return a Fix indicating compression was applied."""
        epub = MagicMock()
        issue = MagicMock(
            location="compression",
            description="Compression level 9 applied",
        )
        fixes = CompressionProcessor().fix(epub, [issue], {"compress": 9})
        assert len(fixes) == 1
        assert "recompressed" in fixes[0].description.lower()
