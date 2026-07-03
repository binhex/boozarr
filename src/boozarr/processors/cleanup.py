"""HTML cleanup processor — strips empty elements from XHTML content."""

from __future__ import annotations

import re
from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

# Matches empty block/inline elements: <p></p>, <div></div>, <span></span>
# with optional whitespace-only content between the tags.
_EMPTY_ELEMENT_RE = re.compile(r"<(p|div|span)\b[^>]*>\s*</\1>", re.IGNORECASE)

# Matches leading non-breaking spaces (and regular spaces) after a <p>,
# <div>, or <span> opening tag — a common pre-CSS technique for paragraph
# indentation.
_LEADING_NBSP_RE = re.compile(r"(<(?:p|div|span)\b[^>]*>)(?:&nbsp;|&#160;|\xa0|\s)+", re.IGNORECASE)


class CleanupProcessor(BaseProcessor):
    name = "cleanup"

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        """Scan XHTML files for empty elements that create unwanted spacing."""
        if config is None or not config.get("cleanup"):
            return []
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []
        issues: list[Issue] = []
        total = 0
        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
            file_issue, file_count = CleanupProcessor._check_file(xhtml_file)
            if file_issue is not None:
                issues.append(file_issue)
                total += file_count
        if total > 0:
            issues.insert(
                0,
                Issue(
                    processor=self.name,
                    severity="info",
                    location="archive",
                    description=f"Total {total} empty element(s) across {len(issues)} file(s)",
                    fix_possible=True,
                ),
            )
        return issues

    @staticmethod
    def _check_file(xhtml_file: Any) -> tuple[Issue | None, int]:
        """Check one XHTML file for empty elements. Returns (Issue_or_None, count)."""
        if not xhtml_file.is_file():
            return None, 0
        try:
            content = xhtml_file.read_text(encoding="utf-8")
        except Exception:
            return None, 0
        count = len(_EMPTY_ELEMENT_RE.findall(content))
        nbsp = len(_LEADING_NBSP_RE.findall(content))
        if not count and not nbsp:
            return None, 0
        parts = []
        if count:
            parts.append(f"{count} empty element(s)")
        if nbsp:
            parts.append(f"{nbsp} leading nbsp(s)")
        return (
            Issue(
                processor=CleanupProcessor.name,
                severity="info",
                location=f"xhtml: {xhtml_file.name}",
                description=f"Found {' and '.join(parts)}",
                fix_possible=True,
            ),
            count + nbsp,
        )

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Remove empty elements and leading nbsp from XHTML files.

        Returns a single aggregated Fix so the log shows one concise summary
        line instead of one line per file (reducing log spam for books with
        many XHTML files).
        """
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []
        total_empty = 0
        total_nbsp = 0
        files_changed = 0
        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
            result = CleanupProcessor._fix_file(xhtml_file)
            if result is not None:
                empty_count, nbsp_count = result
                total_empty += empty_count
                total_nbsp += nbsp_count
                files_changed += 1

        if files_changed == 0:
            return []

        return [
            Fix(
                processor=self.name,
                location="",
                description=CleanupProcessor._build_summary(total_empty, total_nbsp, files_changed),
                old_value="",
                new_value="",
            )
        ]

    @staticmethod
    def _build_summary(total_empty: int, total_nbsp: int, files_changed: int) -> str:
        """Build a human-readable summary of cleanup changes."""
        parts: list[str] = []
        if total_empty:
            label = "elements" if total_empty != 1 else "element"
            parts.append(f"{total_empty} empty {label}")
        if total_nbsp:
            parts.append(f"{total_nbsp} leading nbsp")
        file_label = "files" if files_changed != 1 else "file"
        return f"Removed {' and '.join(parts)} across {files_changed} {file_label}"

    @staticmethod
    def _fix_file(xhtml_file: Any) -> tuple[int, int] | None:
        """Clean up empty elements in one XHTML file.

        Returns ``(empty_tag_count, nbsp_count)`` or ``None`` if no changes
        were needed.  The actual file is modified on disk.
        """
        if not xhtml_file.is_file():
            return None
        try:
            content = xhtml_file.read_text(encoding="utf-8")
        except Exception:
            return None
        new_content = content
        empty_count = 0
        nbsp_count = 0
        while True:
            prev = new_content
            before_nbsp = new_content
            new_content = _LEADING_NBSP_RE.sub(r"\1", new_content)
            nbsp_count += len(_LEADING_NBSP_RE.findall(before_nbsp))
            before_empty = new_content
            new_content = _EMPTY_ELEMENT_RE.sub("", new_content)
            empty_count += len(_EMPTY_ELEMENT_RE.findall(before_empty))
            if new_content == prev:
                break
        if new_content == content:
            return None
        xhtml_file.write_text(new_content, encoding="utf-8")
        return (empty_count, nbsp_count)
