"""Broken link checker processor."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from boozarr.processors.base import BaseProcessor, Fix, Issue

_HREF_RE = re.compile(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\'#][^"\']*)["\']', re.IGNORECASE)
_FIX_TAG_RE_TMPL = r'<a\b[^>]*\bhref\s*=\s*["\']{href}["\'][^>]*>(.*?)</a>'


class LinksProcessor(BaseProcessor):
    name = "links"

    @staticmethod
    def _iter_content_files(extract_dir: Any) -> Any:
        """Return a sorted list of .html and .xhtml files in the extract directory."""
        return sorted(p for p in extract_dir.rglob("*") if p.is_file() and p.suffix in (".html", ".xhtml"))

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        """Scan XHTML/HTML files for internal and external links."""
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []

        check_external = bool(config.get("check_external_links", False)) if config else False
        extracted_files = LinksProcessor._collect_extracted_files(extract_dir)

        issues: list[Issue] = []
        for html_file in self._iter_content_files(extract_dir):
            for match in _HREF_RE.finditer(html_file.read_text(encoding="utf-8")):
                issue = LinksProcessor._check_link(
                    match.group(1),
                    extracted_files,
                    check_external,
                    str(html_file.relative_to(extract_dir)),
                )
                if issue is not None:
                    issues.append(issue)
        return issues

    @staticmethod
    def _collect_extracted_files(extract_dir: Any) -> list[str]:
        """Collect all file paths relative to extract_dir."""
        return [str(f.relative_to(extract_dir)) for f in extract_dir.rglob("*") if f.is_file()]

    @staticmethod
    def _check_link(href: str, extracted_files: list[str], check_external: bool, source_file: str = "") -> Issue | None:
        """Check a single href and return an Issue for broken internal links
        or unchecked external links, or None if the link is fine.
        """
        parsed = urlparse(href)
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            return None
        if parsed.scheme in ("http", "https"):
            if not check_external:
                return None
            return Issue(
                processor=LinksProcessor.name,
                severity="info",
                location=f"ext-link: {href}",
                description=f"External link (validation skipped in batch mode): {href}",
                fix_possible=False,
            )
        file_part = href.split("#")[0] if "#" in href else href
        if file_part and not LinksProcessor._target_exists(extracted_files, file_part):
            return Issue(
                processor=LinksProcessor.name,
                severity="warn",
                location=f"link: {source_file}: {href}",
                description=f"Broken internal reference: {href}",
                fix_possible=True,
            )
        return None

    @staticmethod
    def _group_link_issues(
        issues: list[Issue],
    ) -> dict[str, list[str]]:
        """Group broken-link issues by source file, extracting (file_path, href) pairs."""
        file_hrefs: dict[str, list[str]] = {}
        for issue in issues:
            parsed = _parse_issue_location(issue.location or "")
            if parsed is None:
                continue
            file_path, href = parsed
            file_hrefs.setdefault(file_path, []).append(href)
        return file_hrefs

    @staticmethod
    def _strip_broken_tags(content: str, hrefs: list[str]) -> tuple[str, int]:
        """Remove <a> tags for broken hrefs, keeping inner text. Returns (new_content, count_removed)."""
        total_removed = 0
        for href in hrefs:
            fix_pat = re.compile(
                _FIX_TAG_RE_TMPL.format(href=re.escape(href)),
                re.IGNORECASE | re.DOTALL,
            )
            new_content, count = fix_pat.subn(r"\1", content)
            if count > 0:
                content = new_content
                total_removed += count
        return content, total_removed

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Remove broken internal <a> tags, keeping their inner text."""
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []

        file_hrefs = self._group_link_issues(issues)
        if not file_hrefs:
            return []

        grand_total = self._apply_link_fixes(extract_dir, file_hrefs)
        if grand_total == 0:
            return []

        label = "broken link" if grand_total == 1 else "broken links"
        return [
            Fix(
                processor=self.name,
                location="",
                description=f"Removed {grand_total} {label}",
                old_value="",
                new_value="",
            )
        ]

    @staticmethod
    def _apply_link_fixes(extract_dir: Any, file_hrefs: dict[str, list[str]]) -> int:
        """Apply link fixes to files on disk. Returns total number of tags removed."""
        grand_total = 0
        for file_path, hrefs in file_hrefs.items():
            target = extract_dir / file_path
            if not target.is_file():
                continue
            try:
                content = target.read_text(encoding="utf-8")
            except Exception:
                continue
            new_content, removed = LinksProcessor._strip_broken_tags(content, hrefs)
            if removed == 0:
                continue
            try:
                target.write_text(new_content, encoding="utf-8")
            except Exception:
                continue
            grand_total += removed
        return grand_total

    @staticmethod
    def _target_exists(extracted_files: list[str], href: str) -> bool:
        href = href.removeprefix("./")
        return any(f == href or f.endswith("/" + href) for f in extracted_files)


def _parse_issue_location(location: str) -> tuple[str, str] | None:
    """Parse a LinksProcessor issue location string into (file_path, href).

    Locations use the format ``"link: <source_file>: <href>"``.
    Returns None for non-link locations (e.g. ``"ext-link: ..."``).
    """
    if "ext-link" in location or not location.startswith("link: "):
        return None
    rest = location[len("link: ") :]
    idx = rest.rfind(": ")
    if idx == -1:
        return None
    return (rest[:idx], rest[idx + 2 :])
