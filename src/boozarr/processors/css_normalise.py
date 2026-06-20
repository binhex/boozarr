"""CSS font/line-height/paragraph normalisation processor."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.processors.base import BaseProcessor, Fix, Issue

_PARAGRAPH_PROPS = ["font-size", "line-height", "text-align"]

_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_RULESET_RE = re.compile(r"([^{]+)\{([^}]*)\}")
_CSS_PROPERTY_RE = re.compile(r"([\w-]+)\s*:\s*(.+?)\s*(?:;|$)")


class CssNormaliseProcessor(BaseProcessor):
    name = "css_normalise"

    @staticmethod
    def _scan_css_files(extract_dir: Path, props: dict[str, str]) -> None:
        for css_file in extract_dir.rglob("*.css"):
            if css_file.is_file():
                CssNormaliseProcessor._parse_css_file(css_file, props)

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
                _parse_css_text(style_match.group(1), props)

    @staticmethod
    def _collect_paragraph_props(extract_dir: Path) -> dict[str, str]:
        """Scan CSS and <style> blocks for paragraph-level property:value pairs."""
        props: dict[str, str] = {}
        CssNormaliseProcessor._scan_css_files(extract_dir, props)
        CssNormaliseProcessor._scan_xhtml_styles(extract_dir, props)
        return props

    @staticmethod
    def _parse_css_file(file_path: Path, props: dict[str, str]) -> None:
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return
        _parse_css_text(content, props)

    @staticmethod
    def _rewrite_css_file(file_path: Path, target_map: dict[str, str]) -> None:
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
                        code = code.replace(full_match, f"{prop}: {target_map[prop]}{suffix}", 1)
                segments[i] = code
            new_body = "".join(segments)
            return f"{selector}{{{new_body}}}"

        new_content = _CSS_RULESET_RE.sub(replace_props, content)
        if new_content != content:
            file_path.write_text(new_content, encoding="utf-8")

    def check(self, epub: Any) -> list[Issue]:
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []
        props = self._collect_paragraph_props(extract_dir)
        issues: list[Issue] = []
        for prop in _PARAGRAPH_PROPS:
            val = props.get(prop)
            if val and val not in ("1em", "1.5", "left", "0"):
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
            target_map["font-size"] = font_val
        line_val = config.get("line_height")
        if line_val is not None:
            target_map["line-height"] = line_val
        text_val = config.get("text_align")
        if text_val is not None:
            target_map["text-align"] = text_val
        return target_map

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Replace non-standard CSS values using a target map built from config.

        The target map is built by :meth:`_build_target_map`. Only properties
        present in that map are rewritten; fixes are only returned for issues
        whose property has a configured target.
        """
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []
        target_map = self._build_target_map(config)
        for css_file in extract_dir.rglob("*.css"):
            if css_file.is_file():
                self._rewrite_css_file(css_file, target_map)
        return [
            Fix(
                processor=self.name,
                location=i.location,
                description=f"Normalised {i.location}",
                old_value=i.description,
                new_value=target_map.get(i.location.split()[-1].strip("()"), ""),
            )
            for i in issues
            if i.location.split()[-1].strip("()") in target_map
        ]


def _parse_css_text(css_text: str, props: dict[str, str]) -> None:
    """Parse CSS text and populate *props* with paragraph-level property:value pairs."""
    cleaned = _CSS_COMMENT_RE.sub("", css_text)
    for rule_match in _CSS_RULESET_RE.finditer(cleaned):
        body = rule_match.group(2)
        for prop_match in _CSS_PROPERTY_RE.finditer(body):
            prop_name = prop_match.group(1).strip().lower()
            prop_value = prop_match.group(2).strip()
            if prop_name in _PARAGRAPH_PROPS:
                props[prop_name] = prop_value
