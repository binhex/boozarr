"""Broken link checker processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue


class LinksProcessor(BaseProcessor):
    name = "links"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        check_ext = getattr(epub, "check_external_links", False)
        for link in getattr(epub, "internal_links", []):
            if not self._target_exists(epub, link):
                issues.append(
                    Issue(
                        processor=self.name,
                        severity="warn",
                        location=f"link: {link}",
                        description=f"Broken internal reference: {link}",
                        fix_possible=False,
                    )
                )
        if check_ext:
            for link in getattr(epub, "external_links", []):
                issues.append(
                    Issue(
                        processor=self.name,
                        severity="info",
                        location=f"ext-link: {link}",
                        description=f"External link (validation skipped in batch mode): {link}",
                        fix_possible=False,
                    )
                )
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        return []

    @staticmethod
    def _target_exists(epub: Any, href: str) -> bool:
        if "#" in href:
            file_part = href.split("#")[0]
            if file_part:
                extracted = [str(f) for f in getattr(epub, "extracted_files", [])]
                return any(f.endswith(file_part) for f in extracted)
            return True
        extracted = [str(f) for f in getattr(epub, "extracted_files", [])]
        return any(f.endswith(href) for f in extracted)
