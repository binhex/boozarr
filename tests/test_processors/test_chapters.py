"""Tests for ChaptersProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.chapters import ChaptersProcessor


class TestChaptersCheck:
    def test_no_issues_when_toc_populated(self) -> None:
        epub = MagicMock()
        epub.read_ncx.return_value = [{"label": "Ch1", "src": "ch1.xhtml"}]
        issues = ChaptersProcessor().check(epub)
        assert issues == []

    def test_issue_when_toc_empty(self) -> None:
        epub = MagicMock()
        epub.read_ncx.return_value = []
        issues = ChaptersProcessor().check(epub)
        assert len(issues) == 1
        assert issues[0].processor == "chapters"
        assert issues[0].fix_possible is True

    def test_issue_when_toc_missing(self) -> None:
        epub = MagicMock()
        epub.read_ncx.side_effect = Exception("no ncx")
        issues = ChaptersProcessor().check(epub)
        assert len(issues) == 1


class TestChaptersFix:
    def test_fix_discovers_chapters(self) -> None:
        epub = MagicMock()
        epub.xhtml_files = [
            {"path": "OEBPS/ch1.xhtml", "content": "<html><body><h1>Chapter 1</h1><p>text</p></body></html>"},
            {"path": "OEBPS/ch2.xhtml", "content": "<html><body><h1>Chapter 2</h1><p>text</p></body></html>"},
        ]
        issues = [MagicMock()]
        fixes = ChaptersProcessor().fix(epub, issues, {})  # type: ignore[arg-type]
        assert len(fixes) >= 1
