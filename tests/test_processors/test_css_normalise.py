"""Tests for CssNormaliseProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.css_normalise import CssNormaliseProcessor


class TestCssNormaliseCheck:
    def test_no_issues_when_standard(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"font-size": "1em", "line-height": "1.5", "text-align": "left"}
        assert CssNormaliseProcessor().check(epub) == []

    def test_issue_on_nonstandard_font_size(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"font-size": "2em", "line-height": "1.5"}
        issues = CssNormaliseProcessor().check(epub)
        assert len(issues) == 1

    def test_issue_on_nonstandard_margin(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"font-size": "1em", "margin": "2em"}
        issues = CssNormaliseProcessor().check(epub)
        assert len(issues) == 1


class TestCssNormaliseFix:
    def test_fix_applies_mapped_values(self) -> None:
        epub = MagicMock()
        issue = MagicMock(location="CSS (font-size)", description="Non-standard font-size: '2em'")
        fixes = CssNormaliseProcessor().fix(epub, [issue], {"font_size": "1em"})
        assert len(fixes) == 1
        assert "1em" in fixes[0].new_value
