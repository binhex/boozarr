"""Tests for LinksProcessor."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.processors.links import LinksProcessor


def _make_epub_with_files(base_dir: Path, files: dict[str, str]) -> MagicMock:
    """Create a mock epub with an extract dir containing the given files.

    Uses *base_dir* (provided by the ``tmp_path`` fixture) for automatic cleanup.
    """
    for relpath, content in files.items():
        fpath = base_dir / relpath
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    epub = MagicMock()
    epub._extract_dir = base_dir
    return epub


class TestLinksCheck:
    def test_no_issues_when_all_links_valid(self, tmp_path: Path) -> None:
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<a href="ch2.xhtml">link</a>',
                "OEBPS/ch2.xhtml": "<html/>",
            },
        )
        issues = LinksProcessor().check(epub)
        assert issues == []

    def test_issue_on_broken_link(self, tmp_path: Path) -> None:
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<a href="missing.xhtml">link</a>',
            },
        )
        issues = LinksProcessor().check(epub)
        assert len(issues) == 1
        assert "Broken" in issues[0].description

    def test_issue_on_external_link(self, tmp_path: Path) -> None:
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<a href="https://example.com/missing">link</a>',
            },
        )
        issues = LinksProcessor().check(epub, {"check_external_links": True})
        assert len(issues) == 1
        assert "External" in issues[0].description

    def test_external_link_ignored_when_not_configured(self, tmp_path: Path) -> None:
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<a href="https://example.com/missing">link</a>',
            },
        )
        issues = LinksProcessor().check(epub)
        assert issues == []

    def test_anchor_link_with_file(self, tmp_path: Path) -> None:
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<a href="ch1.xhtml#section1">link</a>',
            },
        )
        issues = LinksProcessor().check(epub)
        assert issues == []

    def test_anchor_same_file(self, tmp_path: Path) -> None:
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<a href="#section1">link</a>',
            },
        )
        issues = LinksProcessor().check(epub)
        assert issues == []

    def test_broken_link_is_fixable(self, tmp_path: Path) -> None:
        """A broken internal link should have fix_possible=True so fix() can act."""
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<a href="missing.xhtml">click here</a>',
            },
        )
        issues = LinksProcessor().check(epub)
        assert len(issues) == 1
        assert issues[0].fix_possible is True

    def test_no_extract_dir_returns_empty(self) -> None:
        epub = MagicMock()
        epub._extract_dir = None
        issues = LinksProcessor().check(epub)
        assert issues == []

    def test_mailto_link_ignored(self, tmp_path: Path) -> None:
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<a href="mailto:user@example.com">email</a>',
            },
        )
        issues = LinksProcessor().check(epub)
        assert issues == []

    def test_javascript_link_ignored(self, tmp_path: Path) -> None:
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<a href="javascript:void(0)">click</a>',
            },
        )
        issues = LinksProcessor().check(epub)
        assert issues == []


class TestLinksFix:
    def test_fix_removes_broken_link_tag(self, tmp_path: Path) -> None:
        """fix() should strip the <a> tag for broken internal links, keeping inner text."""
        epub = _make_epub_with_files(
            tmp_path,
            {
                "OEBPS/ch1.xhtml": '<p>Read <a href="missing.xhtml">this chapter</a> for details.</p>',
            },
        )
        processor = LinksProcessor()
        issues = processor.check(epub)
        assert len(issues) == 1, f"Expected 1 issue, got {len(issues)}"

        fixes = processor.fix(epub, issues, {})
        assert len(fixes) == 1, f"Expected 1 fix, got {len(fixes)}"

        content = (tmp_path / "OEBPS/ch1.xhtml").read_text(encoding="utf-8")
        assert "this chapter" in content, "Inner text should be preserved"
        assert '<a href="missing.xhtml"' not in content, "Broken <a> tag should be removed"
        assert 'href="missing.xhtml"' not in content, "href should be removed"
