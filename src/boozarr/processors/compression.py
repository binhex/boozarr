"""Compression and cleanup processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_EXTRA = {".DS_Store", "thumbs.db", "Thumbs.db", "desktop.ini"}


class CompressionProcessor(BaseProcessor):
    name = "compression"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        extra = [f for f in getattr(epub, "extra_files", []) if f.name in _EXTRA]
        if extra:
            issues.append(
                Issue(
                    processor=self.name,
                    severity="info",
                    location="archive root",
                    description=f"Found {len(extra)} extraneous file(s): {[e.name for e in extra]}",
                    fix_possible=True,
                )
            )
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        return [
            Fix(
                processor=self.name,
                location=i.location,
                description="Stripped extraneous files",
                old_value=i.description,
                new_value="cleaned",
            )
            for i in issues
        ]
