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
        """Remove empty <p>, <div>, and <span> elements from XHTML files."""
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []
        fixes: list[Fix] = []
        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
            fix = CleanupProcessor._fix_file(xhtml_file)
            if fix is not None:
                fixes.append(fix)
        return fixes

    @staticmethod
    def _fix_file(xhtml_file: Any) -> Fix | None:
        """Clean up empty elements in one XHTML file. Returns Fix or None."""
        if not xhtml_file.is_file():
            return None
        try:
            content = xhtml_file.read_text(encoding="utf-8")
        except Exception:
            return None
        new_content = content
        while True:
            prev = new_content
            new_content = _LEADING_NBSP_RE.sub(r"\1", new_content)
            new_content = _EMPTY_ELEMENT_RE.sub("", new_content)
            if new_content == prev:
                break
        if new_content == content:
            return None
        xhtml_file.write_text(new_content, encoding="utf-8")
        count = len(_EMPTY_ELEMENT_RE.findall(content))
        nbsp_count = len(_LEADING_NBSP_RE.findall(content))
        parts = []
        old_parts = []
        if count:
            parts.append(f"{count} empty element(s)")
            old_parts.append(f"{count} empty tags")
        if nbsp_count:
            parts.append(f"{nbsp_count} leading nbsp(s)")
            old_parts.append(f"{nbsp_count} leading nbsp")
        return Fix(
            processor=CleanupProcessor.name,
            location=f"xhtml: {xhtml_file.name}",
            description=f"Stripped {'; '.join(parts)}",
            old_value=", ".join(old_parts),
            new_value="removed",
        )
