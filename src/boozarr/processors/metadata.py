"""Missing metadata fixer processor."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_REQUIRED = ["dc:title", "dc:creator", "dc:language", "dc:date"]


class MetadataProcessor(BaseProcessor):
    name = "metadata"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        meta = getattr(epub, "opf_metadata", {})
        for field in _REQUIRED:
            if not meta.get(field):
                issues.append(
                    Issue(
                        processor=self.name,
                        severity="warn",
                        location="content.opf <metadata>",
                        description=f"Missing {field}",
                        fix_possible=True,
                    )
                )
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        filename = getattr(epub, "path", None)
        fname = str(filename) if filename else ""
        match = re.match(r"(.+?)\s*-\s*(.+?)\.epub", fname.rsplit("/", 1)[-1])
        if match:
            author = match.group(1).strip()
            title = match.group(2).strip()
        else:
            author = "Unknown Author"
            title = Path(fname).stem if fname else "Unknown Title"
        return [self._resolve_fix(issue, author, title) for issue in issues]

    @staticmethod
    def _resolve_fix(issue: Issue, author: str, title: str) -> Fix:
        """Return a Fix for a single metadata issue based on its field name."""
        # Extract field name from description e.g. "Missing dc:title" → "dc:title"
        field = issue.description.replace("Missing ", "", 1) if issue.description.startswith("Missing ") else ""
        specs = {
            "dc:title": (f"Inferred title '{title}'", title),
            "dc:creator": (f"Inferred author '{author}'", author),
            "dc:language": ("Defaulted language to 'en'", "en"),
            "dc:date": ("Defaulted date to today", "2026-01-01"),
        }
        desc, new_val = specs.get(field, ("Unknown field", ""))
        return Fix(issue.processor, issue.location, desc, "", new_val)
