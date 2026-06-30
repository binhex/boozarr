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
        extract_dir = getattr(epub, "_extract_dir", None)
        extra_names = CompressionProcessor._find_extraneous(extract_dir)
        if extra_names:
            issues.append(
                Issue(
                    processor=self.name,
                    severity="info",
                    location="archive root",
                    description=f"Found {len(extra_names)} extraneous file(s): {extra_names}",
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

    @staticmethod
    def _find_extraneous(extract_dir: Any) -> list[str]:
        """Find extraneous files (DS_Store, thumbs.db) in the extract dir."""
        if extract_dir is None:
            return []
        extra_lower = {e.lower() for e in _EXTRA}
        return [f.name for f in extract_dir.iterdir() if f.is_file() and f.name.lower() in extra_lower]

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
