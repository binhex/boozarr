"""Broken link checker processor."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from boozarr.processors.base import BaseProcessor, Fix, Issue

_HREF_RE = re.compile(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\'#][^"\']*)["\']', re.IGNORECASE)


class LinksProcessor(BaseProcessor):
    name = "links"

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        """Scan XHTML/HTML files for internal and external links."""
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []

        check_external = bool(config.get("check_external_links", False)) if config else False
        extracted_files = LinksProcessor._collect_extracted_files(extract_dir)

        issues: list[Issue] = []
        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
            if not xhtml_file.is_file():
                continue
            try:
                content = xhtml_file.read_text(encoding="utf-8")
            except Exception:
                continue
            for match in _HREF_RE.finditer(content):
                issue = LinksProcessor._check_link(match.group(1), extracted_files, check_external)
                if issue is not None:
                    issues.append(issue)
        return issues

    @staticmethod
    def _collect_extracted_files(extract_dir: Any) -> list[str]:
        """Collect all file paths relative to extract_dir."""
        return [str(f.relative_to(extract_dir)) for f in extract_dir.rglob("*") if f.is_file()]

    @staticmethod
    def _check_link(href: str, extracted_files: list[str], check_external: bool) -> Issue | None:
        """Check a single href and return an Issue if it's broken, or None."""
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
                location=f"link: {href}",
                description=f"Broken internal reference: {href}",
                fix_possible=False,
            )
        return None

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        return []

    @staticmethod
    def _target_exists(extracted_files: list[str], href: str) -> bool:
        href = href.removeprefix("./")
        return any(f == href or f.endswith("/" + href) for f in extracted_files)
