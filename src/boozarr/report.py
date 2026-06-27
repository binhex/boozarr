"""Console summary reporting for boozarr processing runs."""

from __future__ import annotations

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
        dry_run: bool = False,
    ) -> str:
        """Format and store a per-file status line.

        ``dry_run`` is appended to the line as a suffix when True.
        """
        self.total += 1
        self.total_issues += issues
        self.total_fixes += fixes
        filename = file_path
        if status == "ok":
            tag = "[OK]"
        elif status == "warn":
            tag = "[MODIFY]"
        elif status == "error":
            tag = "[ERR]"
            self.errors += 1
        elif status == "skip":
            tag = "[SKIP]"
            self.skipped += 1
        else:
            tag = f"[?{status.upper()}?]"
            self.errors += 1
        suffix = " (dry-run)" if dry_run else ""
        line = f"{tag:8} {filename} — {issues} issues, {fixes} fixes{suffix}"
        if fix_details:
            line += "\n" + "\n".join(f"         - {d}" for d in fix_details)
            self._fix_details_list.extend(fix_details)
        self._lines.append(line)
        return line

    def final_summary(self, duration_s: float) -> str:
        """Render a table-style summary with aligned columns and box-drawing dividers.

        Includes file/issue/fix counts and a per-processor fix breakdown when
        ``_fix_details_list`` is non-empty.
        """
        from collections import defaultdict

        lines: list[str] = []

        # ─ top border
        lines.append("─" * 40)

        lines.append(f"  Files processed:  {self.total}  ({self.skipped} skipped, {self.errors} errors)")
        lines.append(f"  Issues found:     {self.total_issues}")
        lines.append(f"  Fixes applied:    {self.total_fixes}")

        if self._fix_details_list:
            # Group changes by processor
            groups: dict[str, list[str]] = defaultdict(list)
            for detail in self._fix_details_list:
                if ":" in detail:
                    processor, _ = detail.split(":", 1)
                    processor = processor.strip()
                else:
                    processor = "unknown"
                groups[processor].append(detail)

            lines.append("")
            lines.append("  Fixes by processor:")
            for proc in sorted(groups):
                count = len(groups[proc])
                padded_proc = proc.ljust(18)
                lines.append(f"    {padded_proc}{count}")

        # ─ bottom border
        lines.append("─" * 40)
        lines.append(f"  Duration: {duration_s:.1f}s")

        return "\n".join(lines)
