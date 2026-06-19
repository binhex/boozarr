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

    def test_issue_when_ds_store_present(self) -> None:
        epub = MagicMock()
        epub.extra_files = [Path(".DS_Store"), Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub)
        assert len(issues) == 1


class TestCompressionFix:
    def test_fix_cleans_extraneous(self) -> None:
        epub = MagicMock()
        issue = MagicMock(
            location="archive root",
            description="Found 1 extraneous file(s)",
        )
        fixes = CompressionProcessor().fix(epub, [issue], {})
        assert len(fixes) == 1
        assert "cleaned" in fixes[0].new_value
