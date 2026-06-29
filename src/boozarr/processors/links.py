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
        """Scan XHTML/HTML files for internal and external links.

        Internal links are checked against the list of files in the
        extracted EPUB directory. External links are reported but not
        validated (batch mode).
        """
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []

        check_external = bool(config.get("check_external_links", False)) if config else False

        # Collect all file paths in the extracted tree for target resolution
        extracted_files = [str(f.relative_to(extract_dir)) for f in extract_dir.rglob("*") if f.is_file()]

        issues: list[Issue] = []
        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
            if not xhtml_file.is_file():
                continue
            try:
                content = xhtml_file.read_text(encoding="utf-8")
            except Exception:
                continue
            for match in _HREF_RE.finditer(content):
                href = match.group(1)
                parsed = urlparse(href)
                # Skip non-file URI schemes (mailto:, javascript:, tel:, ftp:, etc.)
                if parsed.scheme and parsed.scheme not in ("http", "https"):
                    continue
                if parsed.scheme in ("http", "https"):
                    if check_external:
                        issues.append(
                            Issue(
                                processor=self.name,
                                severity="info",
                                location=f"ext-link: {href}",
                                description=f"External link (validation skipped in batch mode): {href}",
                                fix_possible=False,
                            )
                        )
                else:
                    # Internal link — resolve fragment and file part
                    file_part = href.split("#")[0] if "#" in href else href
                    if file_part and not self._target_exists(extracted_files, file_part):
                        issues.append(
                            Issue(
                                processor=self.name,
                                severity="warn",
                                location=f"link: {href}",
                                description=f"Broken internal reference: {href}",
                                fix_possible=False,
                            )
                        )
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        return []

    @staticmethod
    def _target_exists(extracted_files: list[str], href: str) -> bool:
        href = href.removeprefix("./")
        return any(f == href or f.endswith("/" + href) for f in extracted_files)
