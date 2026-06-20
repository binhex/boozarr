"""Pipeline orchestrator — runs processors in sequence per EPUB file."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import traceback
import zipfile
from pathlib import Path
from typing import Any

from boozarr.epub import EpubWrapper


class Pipeline:
    def __init__(
        self,
        db: Any,
        processors: list[Any],
        config: dict[str, Any],
        fix: bool = False,
        backup: bool = True,
    ) -> None:
        self.db = db
        self.processors = processors
        self.config = config
        self.fix = fix
        self.backup = backup
        self.config_hash = self._compute_config_hash({"fix": fix, **config})

    @staticmethod
    def _compute_config_hash(config: dict[str, Any]) -> str:
        """Compute a deterministic hash of the config dict for skip logic."""
        raw = json.dumps(config, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _should_skip(self, file_hash: str) -> bool:
        try:
            existing = self.db.lookup(file_hash, self.config_hash)
        except AttributeError:
            existing = self.db.lookup_hash(file_hash)
        return bool(existing in ("ok", "warn"))

    def _make_error(self, epub_path: Path, exc: Exception) -> dict[str, Any]:
        return {
            "file_path": str(epub_path),
            "status": "error",
            "issues": 0,
            "fixes": 0,
            "error": str(exc),
            "fix_details": [],
        }

    def _record_and_return(
        self,
        epub_path: Path,
        wrapper: EpubWrapper,
        overall: str,
        total_issues: int,
        total_fixes: int,
        fix_details: list[str],
    ) -> dict[str, Any]:
        """Record the result in the DB and return a status dictionary.

        The returned dictionary includes a ``dry_run`` key that is True when
        ``self.fix`` is False.
        """
        if overall == "error":
            status = "error"
        elif total_issues == 0:
            status = "ok"
        else:
            status = "warn"
        self.db.record_file(
            str(epub_path),
            wrapper.file_hash,
            status,
            total_issues,
            total_fixes,
            dry_run=not self.fix,
            config_hash=self.config_hash,
        )
        return {
            "file_path": str(epub_path),
            "status": status,
            "issues": total_issues,
            "fixes": total_fixes,
            "fix_details": fix_details,
            "dry_run": not self.fix,
        }

    def process_epub(self, epub_path: Path) -> dict[str, Any]:
        """Validate and process one EPUB through the configured processors.

        The EPUB is extracted in both fix and dry-run modes so processors can
        inspect contents; the archive is only repacked when ``self.fix`` is True.
        """
        try:
            wrapper = EpubWrapper(epub_path)
            wrapper.validate()
        except (FileNotFoundError, PermissionError, ValueError, OSError, zipfile.BadZipFile) as exc:
            return self._make_error(epub_path, exc)

        if self._should_skip(wrapper.file_hash):
            return {
                "file_path": str(epub_path),
                "status": "skip",
                "issues": 0,
                "fixes": 0,
                "fix_details": [],
                "dry_run": not self.fix,
            }

        extract_dir = Path(tempfile.mkdtemp(prefix="boozarr_"))
        try:
            wrapper.extract(extract_dir)
            total_issues, total_fixes, overall, fix_details = self._run_processors(wrapper, epub_path)
            if self.fix:
                # Create backup before modifying (only in fix mode)
                if self.backup:
                    bak_path = epub_path.with_suffix(".epub.bak")
                    if not bak_path.exists():
                        shutil.copy2(str(epub_path), str(bak_path))
                # Write to temp path then rename atomically to avoid data loss on crash
                tmp_path = epub_path.with_suffix(".epub.tmp")
                wrapper.repack(tmp_path)
                tmp_path.replace(epub_path)
                # Recompute hash from the (now modified) file
                wrapper.refresh_hash()
            # else: dry-run — don't repack, don't create backup
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

        return self._record_and_return(epub_path, wrapper, overall, total_issues, total_fixes, fix_details)

    def _run_processors(self, wrapper: EpubWrapper, epub_path: Path) -> tuple[int, int, str, list[str]]:
        """Run each processor's check and collect fix details.

        ``fix()`` is called whenever issues are found so details can be
        reported, but fixes are only counted and persisted when ``self.fix`` is
        True.

        Returns a tuple of ``(total_issues, total_fixes, overall_status,
        fix_details)``.
        """
        total_issues = 0
        total_fixes = 0
        overall = "ok"
        fix_details: list[str] = []
        for proc in self.processors:
            try:
                issues = proc.check(wrapper)
                total_issues += len(issues)
                self.db.log_event(str(epub_path), proc.name, "check", f"{len(issues)} issues")
                if issues:
                    fixes = proc.fix(wrapper, issues, self.config)
                    total_fixes += len(fixes) if self.fix else 0
                    if fixes:
                        self.db.log_event(
                            str(epub_path), proc.name, "fix" if self.fix else "dry-run", f"{len(fixes)} fixes"
                        )
                        for fix in fixes:
                            desc = getattr(fix, "description", str(fix))
                            fix_details.append(f"{proc.name}: {desc}")
            except Exception:
                self.db.log_event(str(epub_path), proc.name, "error", traceback.format_exc())
                overall = "error"
        return total_issues, total_fixes, overall, fix_details
