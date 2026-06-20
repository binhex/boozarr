"""CSS border/margin/padding normalisation processor."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.processors.base import BaseProcessor, Fix, Issue

_TARGET = [
    "border",
    "margin",
    "padding",
    "margin-left",
    "margin-right",
    "padding-left",
    "padding-right",
]

# CSS comments and property:value regex
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_RULESET_RE = re.compile(r"([^{]+)\{([^}]*)\}")
_CSS_PROPERTY_RE = re.compile(r"([\w-]+)\s*:\s*(.+?)\s*(?:;|$)")
# Extract the CSS value from a description like "Non-standard padding: '10px'"
_OLD_VALUE_RE = re.compile(r"'([^']+)'")


class BordersProcessor(BaseProcessor):
    name = "borders"

    @staticmethod
    def _scan_css_files(extract_dir: Path, props: dict[str, str]) -> None:
        for css_file in extract_dir.rglob("*.css"):
            if not css_file.is_file():
                continue
            try:
                content = css_file.read_text(encoding="utf-8")
            except Exception:
                continue
            BordersProcessor._parse_css_content(content, props)

    @staticmethod
    def _scan_xhtml_styles(extract_dir: Path, props: dict[str, str]) -> None:
        for xhtml_file in extract_dir.rglob("*.xhtml"):
            if not xhtml_file.is_file():
                continue
            try:
                content = xhtml_file.read_text(encoding="utf-8")
            except Exception:
                continue
            for style_match in re.finditer(r"<style[^>]*>(.*?)</style>", content, re.IGNORECASE | re.DOTALL):
                BordersProcessor._parse_css_content(style_match.group(1), props)

    @staticmethod
    def _collect_css_properties(extract_dir: Path) -> dict[str, str]:
        """Scan all CSS files and inline <style> blocks for property:value pairs."""
        props: dict[str, str] = {}
        BordersProcessor._scan_css_files(extract_dir, props)
        BordersProcessor._scan_xhtml_styles(extract_dir, props)
        return props

    @staticmethod
    def _parse_css_content(css_text: str, props: dict[str, str]) -> None:
        """Parse a block of CSS text and populate *props* with property:value pairs."""
        cleaned = _CSS_COMMENT_RE.sub("", css_text)
        for rule_match in _CSS_RULESET_RE.finditer(cleaned):
            body = rule_match.group(2)
            for prop_match in _CSS_PROPERTY_RE.finditer(body):
                prop_name = prop_match.group(1).strip().lower()
                prop_value = prop_match.group(2).strip()
                if prop_name in _TARGET:
                    props[prop_name] = prop_value

    @staticmethod
    def _rewrite_css_file(file_path: Path, target_map: dict[str, str]) -> None:
        """Rewrite a CSS file, replacing target property values."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return

        def replace_props(match: re.Match) -> str:
            selector = match.group(1)
            body = match.group(2)
            # Split body into code and comment segments so replacements never
            # accidentally modify text inside CSS comments.
            segments: list[str] = []
            last_end = 0
            for cm in _CSS_COMMENT_RE.finditer(body):
                if cm.start() > last_end:
                    segments.append(body[last_end : cm.start()])  # code
                segments.append(cm.group(0))  # comment
                last_end = cm.end()
            if last_end < len(body):
                segments.append(body[last_end:])  # trailing code
            # Only process code segments (even indices)
            for i in range(0, len(segments), 2):
                code = segments[i]
                for prop_match in _CSS_PROPERTY_RE.finditer(code):
                    prop = prop_match.group(1).strip().lower()
                    if prop in target_map:
                        full_match = prop_match.group(0)
                        has_semi = full_match.rstrip().endswith(";")
                        suffix = ";" if has_semi else ""
                        new_decl = f"{prop}: {target_map[prop]}{suffix}"
                        code = code.replace(full_match, new_decl, 1)
                segments[i] = code
            new_body = "".join(segments)
            return f"{selector}{{{new_body}}}"

        new_content = _CSS_RULESET_RE.sub(replace_props, content)
        if new_content != content:
            file_path.write_text(new_content, encoding="utf-8")

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        """Scan CSS files and report non-standard values for configured properties only.

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
        issues: list[Issue] = []
        for prop, target in target_map.items():
            val = props.get(prop)
            if val and val.lower() != target.lower():
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
        border_val = config.get("border")
        if border_val is not None:
            target_map["border"] = border_val
        margin_val = config.get("margin")
        if margin_val is not None:
            target_map["margin"] = margin_val
            target_map["margin-left"] = margin_val
            target_map["margin-right"] = margin_val
        padding_val = config.get("padding")
        if padding_val is not None:
            target_map["padding"] = padding_val
            target_map["padding-left"] = padding_val
            target_map["padding-right"] = padding_val
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

        # Apply fixes to all CSS files
        for css_file in extract_dir.rglob("*.css"):
            if css_file.is_file():
                self._rewrite_css_file(css_file, target_map)

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
