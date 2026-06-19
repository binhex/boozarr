"""Console summary reporting for boozarr processing runs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Report:
    total: int = 0
    skipped: int = 0
    errors: int = 0
    total_issues: int = 0
    total_fixes: int = 0
    _lines: list[str] = field(default_factory=list, repr=False)
    _fix_details_list: list[str] = field(default_factory=list, repr=False)

    def log_line(
        self,
        file_path: str,
        status: str,
        issues: int = 0,
        fixes: int = 0,
        fix_details: list[str] | None = None,
    ) -> str:
        self.total += 1
        self.total_issues += issues
        self.total_fixes += fixes
        filename = file_path.rsplit("/", 1)[-1]
        if status == "ok":
            tag = "[OK]"
        elif status == "warn":
            tag = "[WARN]"
        elif status == "error":
            tag = "[ERR]"
            self.errors += 1
        elif status == "skip":
            tag = "[SKIP]"
            self.skipped += 1
        else:
            tag = f"[?{status.upper()}?]"
            self.errors += 1
        line = f"{tag:8} {filename:50} — {issues} issues, {fixes} fixes"
        if fix_details:
            line += "\n" + "\n".join(f"         - {d}" for d in fix_details)
            self._fix_details_list.extend(fix_details)
        self._lines.append(line)
        return line

    def final_summary(self, duration_s: float) -> str:
        summary = (
            f"Processed: {self.total} files\n"
            f"  - Unchanged (skipped): {self.skipped}\n"
            f"  - Issues found: {self.total_issues} across {self.total - self.skipped - self.errors} files\n"
            f"  - Fixes applied: {self.total_fixes}\n"
        )
        if self._fix_details_list:
            counter: Counter = Counter()
            for d in self._fix_details_list:
                processor = d.split(":", 1)[0] if ":" in d else "unknown"
                counter[processor] += 1
            parts = "  Fixes by processor:\n"
            for proc, count in sorted(counter.items()):
                parts += f"    - {proc}: {count}\n"
            summary += parts
        summary += f"  - Errors: {self.errors}\n"
        summary += f"Duration: {duration_s:.1f}s"
        return summary
