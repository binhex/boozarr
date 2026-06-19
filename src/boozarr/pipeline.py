"""Pipeline orchestrator — runs processors in sequence per EPUB file."""

from __future__ import annotations

import traceback
import zipfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.epub import EpubWrapper


class Pipeline:
    def __init__(
        self,
        db: Any,
        processors: list[Any],
        config: dict[str, Any],
        fix: bool = False,
        backup: bool = False,
    ) -> None:
        self.db = db
        self.processors = processors
        self.config = config
        self.fix = fix
        self.backup = backup

    def process_epub(self, epub_path: Path) -> dict[str, Any]:
        try:
            wrapper = EpubWrapper(epub_path)
            wrapper.validate()
        except (FileNotFoundError, PermissionError, ValueError, OSError, zipfile.BadZipFile) as exc:
            return {"file_path": str(epub_path), "status": "error", "issues": 0, "fixes": 0, "error": str(exc)}

        existing = self.db.lookup_hash(wrapper.file_hash)
        if existing == "ok":
            return {"file_path": str(epub_path), "status": "skip", "issues": 0, "fixes": 0}

        total_issues, total_fixes, overall = self._run_processors(wrapper, epub_path)

        if overall == "error":
            status = "error"
        elif total_issues == 0:
            status = "ok"
        else:
            status = "warn"
        self.db.record_file(str(epub_path), wrapper.file_hash, status, total_issues, total_fixes, dry_run=not self.fix)
        return {"file_path": str(epub_path), "status": status, "issues": total_issues, "fixes": total_fixes}

    def _run_processors(self, wrapper: EpubWrapper, epub_path: Path) -> tuple[int, int, str]:
        """Run each processor's check (and optionally fix) on the EPUB.

        Returns (total_issues, total_fixes, overall_status).
        """
        total_issues = 0
        total_fixes = 0
        overall = "ok"
        for proc in self.processors:
            try:
                issues = proc.check(wrapper)
                total_issues += len(issues)
                self.db.log_event(str(epub_path), proc.name, "check", f"{len(issues)} issues")
                if self.fix and issues:
                    fixes = proc.fix(wrapper, issues, self.config)
                    total_fixes += len(fixes)
                    self.db.log_event(str(epub_path), proc.name, "fix", f"{len(fixes)} fixes")
            except Exception:
                self.db.log_event(str(epub_path), proc.name, "error", traceback.format_exc())
                overall = "error"
        return total_issues, total_fixes, overall
