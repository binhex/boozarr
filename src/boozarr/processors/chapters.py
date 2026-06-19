"""Chapter detection and ToC injection processor."""

from __future__ import annotations

import re
from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_CHAPTER_PATTERNS = [
    re.compile(r"Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"Part\s+\d+", re.IGNORECASE),
    re.compile(r"Section\s+\d+", re.IGNORECASE),
    re.compile(r"CHAPTER\s+\w+", re.IGNORECASE),
]


class ChaptersProcessor(BaseProcessor):
    name = "chapters"

    def check(self, epub: Any) -> list[Issue]:
        try:
            entries = epub.read_ncx()
        except Exception:
            entries = []
        if entries:
            return []
        return [
            Issue(
                processor=self.name,
                severity="warn",
                location="toc.ncx / nav.xhtml",
                description="No chapter entries found in table of contents",
                fix_possible=True,
            )
        ]

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        discovered: list[tuple[str, str]] = []
        for xhtml in getattr(epub, "xhtml_files", []):
            content = xhtml.get("content", "")
            path = xhtml.get("path", "")
            for pattern in _CHAPTER_PATTERNS:
                match = pattern.search(content)
                if match:
                    discovered.append((path, match.group(0)))
                    break
        if discovered:
            from xml.sax.saxutils import escape

            items = " ".join(
                f"<navPoint id='ch-{i}'><navLabel><text>{escape(lab)}</text></navLabel><content src='{escape(p)}'/></navPoint>"
                for i, (p, lab) in enumerate(discovered)
            )
            return [
                Fix(
                    processor=self.name,
                    location="toc.ncx",
                    description=f"Added {len(discovered)} chapter entries",
                    old_value="",
                    new_value=f"<navMap>{items}</navMap>",
                )
            ]
        return []
