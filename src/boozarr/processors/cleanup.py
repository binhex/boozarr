"""HTML cleanup processor — strips empty elements from XHTML content."""

from __future__ import annotations

import re
from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

# Matches empty block/inline elements: <p></p>, <div></div>, <span></span>
# with optional whitespace-only content between the tags.
_EMPTY_ELEMENT_RE = re.compile(
    r"<(p|div|span)\b[^>]*>\s*</\1>", re.IGNORECASE
)


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
            if not xhtml_file.is_file():
                continue
            try:
                content = xhtml_file.read_text(encoding="utf-8")
            except Exception:
                continue
            count = len(_EMPTY_ELEMENT_RE.findall(content))
            if count:
                total += count
                issues.append(
                    Issue(
                        processor=self.name,
                        severity="info",
                        location=f"xhtml: {xhtml_file.name}",
                        description=f"Found {count} empty element(s)",
                        fix_possible=True,
                    )
                )
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

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Remove empty <p>, <div>, and <span> elements from XHTML files."""
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []
        fixes: list[Fix] = []
        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
            if not xhtml_file.is_file():
                continue
            try:
                content = xhtml_file.read_text(encoding="utf-8")
            except Exception:
                continue
            new_content = _EMPTY_ELEMENT_RE.sub("", content)
            if new_content != content:
                xhtml_file.write_text(new_content, encoding="utf-8")
                count = len(_EMPTY_ELEMENT_RE.findall(content))
                fixes.append(
                    Fix(
                        processor=self.name,
                        location=f"xhtml: {xhtml_file.name}",
                        description=f"Stripped {count} empty element(s)",
                        old_value=f"{count} empty tags",
                        new_value="removed",
                    )
                )
        return fixes
