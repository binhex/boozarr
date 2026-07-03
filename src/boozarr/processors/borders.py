"""CSS border/margin/padding normalisation processor."""

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

_TARGET = (
    "border",
    "margin",
    "margin-top",
    "margin-bottom",
    "padding",
    "padding-top",
    "padding-bottom",
    "margin-left",
    "margin-right",
    "padding-left",
    "padding-right",
)

# Extract the CSS value from a description like "Non-standard padding: '10px'"
_OLD_VALUE_RE = re.compile(r"'([^']+)'")


def _set_shorthand(target_map: dict[str, str], config: dict[str, Any], key: str, props: list[str]) -> None:
    """Expand a shorthand property (e.g. margin) into individual CSS properties."""
    val = config.get(key)
    if val is not None:
        normalized = normalize_css_value(val)
        for prop in props:
            target_map[prop] = normalized


def _set_overrides(target_map: dict[str, str], config: dict[str, Any], overrides: list[tuple[str, str]]) -> None:
    """Apply per-side overrides for a property group."""
    for config_key, css_prop in overrides:
        val = config.get(config_key)
        if val is not None:
            target_map[css_prop] = normalize_css_value(val)


class BordersProcessor(BaseProcessor):
    name = "borders"

    @staticmethod
    def _collect_css_properties(extract_dir: Path) -> dict[str, str]:
        """Scan all CSS files and inline <style> blocks for property:value pairs."""
        props: dict[str, str] = {}
        scan_css_files(extract_dir, props, _TARGET)
        scan_xhtml_styles(extract_dir, props, _TARGET)
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

        props = self._collect_css_properties(extract_dir)
        # Normalize collected CSS values for comparison
        normalized_props = {k: normalize_css_value(v) for k, v in props.items()}

        issues: list[Issue] = []
        for prop, target in target_map.items():
            val = normalized_props.get(prop)
            if val and val.lower() != target.lower():
                issues.append(
                    Issue(
                        processor=self.name,
                        severity="info",
                        location=f"CSS ({prop})",
                        description=f"Non-standard {prop}: '{props[prop]}'",
                        fix_possible=True,
                    )
                )
        return issues

    @staticmethod
    def _build_target_map(config: dict[str, Any]) -> dict[str, str]:
        """Build a target map of CSS properties to rewrite, skipping None config values."""
        target_map: dict[str, str] = {}
        _set_shorthand(target_map, config, "border", ["border"])
        _set_shorthand(
            target_map,
            config,
            "margin",
            [
                "margin",
                "margin-left",
                "margin-right",
                "margin-top",
                "margin-bottom",
            ],
        )
        _set_shorthand(
            target_map,
            config,
            "padding",
            [
                "padding",
                "padding-top",
                "padding-bottom",
                "padding-left",
                "padding-right",
            ],
        )
        # Per-side overrides
        _set_overrides(
            target_map,
            config,
            [
                ("margin_top", "margin-top"),
                ("margin_bottom", "margin-bottom"),
                ("margin_left", "margin-left"),
                ("margin_right", "margin-right"),
            ],
        )
        _set_overrides(
            target_map,
            config,
            [
                ("padding_top", "padding-top"),
                ("padding_bottom", "padding-bottom"),
                ("padding_left", "padding-left"),
                ("padding_right", "padding-right"),
            ],
        )
        return target_map

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Replace non-standard CSS values using a target map built from config.

        The target map is built by :meth:`_build_target_map`. Only properties
        present in that map are rewritten; fixes are only returned for issues
        whose property has a configured target.

        Each returned ``Fix`` carries the original CSS value (extracted from
        the issue description via ``_OLD_VALUE_RE``) in ``old_value`` and the
        configured replacement in ``new_value``.
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

        # Build fixes with old_value extracted from the original description
        fixes: list[Fix] = []
        for i in issues:
            prop = i.location.split()[-1].strip("()")
            if prop not in target_map:
                continue
            old_match = _OLD_VALUE_RE.search(i.description)
            old_value = old_match.group(1) if old_match else i.description
            fixes.append(
                Fix(
                    processor=self.name,
                    location=i.location,
                    description=f"Normalised {i.location}",
                    old_value=old_value,
                    new_value=target_map[prop],
                )
            )
        return fixes
