"""Tests for LinksProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.links import LinksProcessor


class TestLinksCheck:
    def test_no_issues_when_all_links_valid(self) -> None:
        epub = MagicMock()
        epub.internal_links = ["ch1.xhtml", "ch2.xhtml"]
        epub.extracted_files = ["/tmp/x/OEBPS/ch1.xhtml", "/tmp/x/OEBPS/ch2.xhtml"]
        issues = LinksProcessor().check(epub)
        assert issues == []

    def test_issue_on_broken_link(self) -> None:
        epub = MagicMock()
        epub.internal_links = ["missing.xhtml"]
        epub.extracted_files = ["/tmp/x/OEBPS/ch1.xhtml"]
        issues = LinksProcessor().check(epub)
        assert len(issues) == 1

    def test_issue_on_external_link(self) -> None:
        epub = MagicMock()
        epub.internal_links = []
        epub.external_links = ["https://example.com/missing"]
        epub.check_external_links = True
        issues = LinksProcessor().check(epub)
        assert len(issues) == 1

    def test_anchor_link_with_file(self) -> None:
        epub = MagicMock()
        epub.internal_links = ["ch1.xhtml#section1"]
        epub.extracted_files = ["/tmp/x/OEBPS/ch1.xhtml"]
        issues = LinksProcessor().check(epub)
        assert issues == []

    def test_anchor_same_file(self) -> None:
        epub = MagicMock()
        epub.internal_links = ["#section1"]
        epub.extracted_files = ["/tmp/x/OEBPS/ch1.xhtml"]
        issues = LinksProcessor().check(epub)
        assert issues == []


class TestLinksFix:
    def test_fix_returns_empty(self) -> None:
        fixes = LinksProcessor().fix(MagicMock(), [], {})
        assert fixes == []
