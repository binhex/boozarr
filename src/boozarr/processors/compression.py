"""Compression and cleanup processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_EXTRA = {".DS_Store", "thumbs.db", "Thumbs.db", "desktop.ini"}


class CompressionProcessor(BaseProcessor):
    name = "compression"

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        if config is None or config.get("compress") is None:
            return []
        # Set the compression level unconditionally so repack() uses it even
        # when there are no extraneous files.
        epub._compress_level = config.get("compress")
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
        # Always report compression as an issue when configured so it appears
        # in the summary under "Fixes by processor".
        issues.append(
            Issue(
                processor=self.name,
                severity="info",
                location="compression",
                description=f"Compression level {config['compress']} applied",
                fix_possible=True,
            )
        )
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        epub._compress_level = config.get("compress")
        fixes: list[Fix] = []
        for i in issues:
            if i.location == "compression":
                fixes.append(
                    Fix(
                        processor=self.name,
                        location=i.location,
                        description=f"EPUB recompressed at level {config['compress']}",
                        old_value="default",
                        new_value=str(config["compress"]),
                    )
                )
            else:
                fixes.append(
                    Fix(
                        processor=self.name,
                        location=i.location,
                        description="Stripped extraneous files",
                        old_value=i.description,
                        new_value="cleaned",
                    )
                )
        return fixes
