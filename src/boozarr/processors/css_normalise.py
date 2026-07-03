"""CSS font/line-height/paragraph normalisation processor."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.processors._css_utils import (
    rewrite_css_file,
    rewrite_inline_styles,
    scan_css_files,
    scan_xhtml_styles,
)
from boozarr.processors.base import BaseProcessor, Fix, Issue
from boozarr.utils import normalize_css_value

_PARAGRAPH_PROPS = ("font-size", "line-height", "text-align", "text-indent")

_OLD_VALUE_RE = re.compile(r"'([^']+)'")


class CssNormaliseProcessor(BaseProcessor):
    name = "css_normalise"

    @staticmethod
    def _collect_paragraph_props(extract_dir: Path) -> dict[str, str]:
        """Scan CSS and <style> blocks for paragraph-level property:value pairs."""
        props: dict[str, str] = {}
        scan_css_files(extract_dir, props, _PARAGRAPH_PROPS)
        scan_xhtml_styles(extract_dir, props, _PARAGRAPH_PROPS)
        return props

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        """Scan CSS files and inline <style> blocks, reporting non-standard values
        for configured properties only.

        When *config* is ``None`` or empty, no issues are reported.
        Each configured property is only reported when its CSS value differs
        from the user's target.
        """
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []

        target_map = self._build_target_map(config or {})
        if not target_map:
            return []

        props = self._collect_paragraph_props(extract_dir)
        # Normalize collected CSS values for comparison (consistent with borders.py)
        normalized_props: dict[str, str] = {}
        for k, v in props.items():
            if k == "font-size":
                normalized_props[k] = normalize_css_value(v)
            else:
                normalized_props[k] = v

        issues: list[Issue] = []
        for prop, target in target_map.items():
            val = normalized_props.get(prop)
            if _value_differs(val, target):
                issues.append(
                    Issue(
                        processor=self.name,
                        severity="info",
                        location=f"CSS ({prop})",
                        description=f"Non-standard {prop}: '{val}'",
                        fix_possible=True,
                    )
                )
        return issues

    @staticmethod
    def _build_target_map(config: dict[str, Any]) -> dict[str, str]:
        """Build a target map of CSS properties to rewrite, skipping None config values."""
        target_map: dict[str, str] = {}
        font_val = config.get("font_size")
        if font_val is not None:
            target_map["font-size"] = normalize_css_value(font_val)
        line_val = config.get("line_height")
        if line_val is not None:
            # line-height can be unitless (e.g., 1.5), store as string for comparison
            target_map["line-height"] = str(line_val)
        text_val = config.get("text_align")
        if text_val is not None:
            target_map["text-align"] = text_val
        indent_val = config.get("text_indent")
        if indent_val is not None:
            target_map["text-indent"] = normalize_css_value(indent_val)
        return target_map

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Replace non-standard CSS values using a target map built from config.

        The target map is built by :meth:`_build_target_map`. Only properties
        present in that map are rewritten; fixes are only returned for issues
        whose property has a configured target.

        Each returned ``Fix`` carries the original CSS value (extracted from
        the issue description via :func:`_extract_old_value`) in ``old_value``
        and the configured replacement in ``new_value``.
        """
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []
        target_map = self._build_target_map(config)
        # Apply fixes to all CSS files and inline <style> blocks
        for css_file in extract_dir.rglob("*.css"):
            if css_file.is_file():
                rewrite_css_file(css_file, target_map)
        rewrite_inline_styles(extract_dir, target_map)
        return [
            Fix(
                processor=self.name,
                location=i.location,
                description=f"Normalised {i.location}",
                old_value=_extract_old_value(i.description),
                new_value=target_map.get(i.location.split()[-1].strip("()"), ""),
            )
            for i in issues
            if i.location.split()[-1].strip("()") in target_map
        ]


def _extract_old_value(description: str) -> str:
    """Extract the CSS value from a description like ``"Non-standard font-size: '2em'"``."""
    m = _OLD_VALUE_RE.search(description)
    if m:
        return m.group(1)
    return description


def _value_differs(val: str | None, target: str) -> bool:
    """Return True if *val* is not None and differs from *target* (case-insensitive)."""
    if val is None:
        return False
    return val.lower() != target.lower()
