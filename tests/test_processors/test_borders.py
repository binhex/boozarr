"""Tests for BordersProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.borders import BordersProcessor


class TestBordersCheck:
    def test_no_issues_when_all_standard(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"border": "none", "margin": "1em", "padding": "0"}
        issues = BordersProcessor().check(epub)
        assert issues == []

    def test_issue_on_nonstandard_border(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"border": "2px solid red", "margin": "1em", "padding": "0"}
        issues = BordersProcessor().check(epub)
        assert len(issues) >= 1

    def test_issue_on_nonstandard_margin(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"margin": "2cm", "border": "none", "padding": "0"}
        issues = BordersProcessor().check(epub)
        assert len(issues) >= 1


class TestBordersFix:
    def test_fix_creates_entry_per_issue(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"border": "2px solid red"}
        issues = BordersProcessor().check(epub)
        fixes = BordersProcessor().fix(epub, issues, {"border": "none"})
        assert len(fixes) == len(issues)
