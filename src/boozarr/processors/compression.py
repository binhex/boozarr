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
        # Scan the extract directory for extraneous files at archive root
        extract_dir = getattr(epub, "_extract_dir", None)
        extra_names: list[str] = []
        if extract_dir is not None:
            for f in extract_dir.iterdir():
                if f.is_file() and f.name.lower() in {e.lower() for e in _EXTRA}:
                    extra_names.append(f.name)
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
