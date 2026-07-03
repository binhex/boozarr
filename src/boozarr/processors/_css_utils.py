"""Shared CSS parsing and rewriting utilities.

Used by BordersProcessor and CssNormaliseProcessor to avoid code
duplication across the two processors that both parse and rewrite
CSS content.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# CSS comments and property:value regex
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_RULESET_RE = re.compile(r"([^{]+)\{([^}]*)\}")
_CSS_PROPERTY_RE = re.compile(r"([\w-]+)\s*:\s*(.+?)\s*(?:;|$)")


def parse_css_properties(
    css_text: str,
    props: dict[str, str],
    target_props: tuple[str, ...],
) -> None:
    """Parse CSS text and populate *props* with property:value pairs
    for properties in *target_props*."""
    cleaned = _CSS_COMMENT_RE.sub("", css_text)
    for rule_match in _CSS_RULESET_RE.finditer(cleaned):
        body = rule_match.group(2)
        for prop_match in _CSS_PROPERTY_RE.finditer(body):
            prop_name = prop_match.group(1).strip().lower()
            prop_value = prop_match.group(2).strip()
            if prop_name in target_props:
                props[prop_name] = prop_value


def scan_css_files(extract_dir: Path, props: dict[str, str], target_props: tuple[str, ...]) -> None:
    """Scan all .css files in *extract_dir* for CSS property:value pairs."""
    for css_file in extract_dir.rglob("*.css"):
        if not css_file.is_file():
            continue
        try:
            content = css_file.read_text(encoding="utf-8")
        except Exception:
            continue
        parse_css_properties(content, props, target_props)


def scan_xhtml_styles(extract_dir: Path, props: dict[str, str], target_props: tuple[str, ...]) -> None:
    """Scan inline <style> blocks in XHTML files for CSS property:value pairs."""
    for xhtml_file in extract_dir.rglob("*.xhtml"):
        if not xhtml_file.is_file():
            continue
        try:
            content = xhtml_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for style_match in re.finditer(r"<style[^>]*>(.*?)</style>", content, re.IGNORECASE | re.DOTALL):
            parse_css_properties(style_match.group(1), props, target_props)


def rewrite_css_text(css_text: str, target_map: dict[str, str]) -> str:
    """Rewrite a block of CSS text, replacing target property values.

    Splits CSS body into code and comment segments so replacements never
    accidentally modify text inside CSS comments.
    """

    def replace_props(match: re.Match) -> str:
        selector = match.group(1)
        body = match.group(2)
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

    return _CSS_RULESET_RE.sub(replace_props, css_text)


def rewrite_css_file(file_path: Path, target_map: dict[str, str]) -> None:
    """Rewrite a CSS file, replacing target property values."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return
    new_content = rewrite_css_text(content, target_map)
    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")


def rewrite_inline_styles(extract_dir: Path, target_map: dict[str, str]) -> None:
    """Rewrite inline <style> blocks inside XHTML files."""
    for xhtml_file in extract_dir.rglob("*.xhtml"):
        if not xhtml_file.is_file():
            continue
        try:
            content = xhtml_file.read_text(encoding="utf-8")
        except Exception:
            continue
        new_content = content
        for style_match in re.finditer(r"(<style[^>]*>)(.*?)(</style>)", content, re.IGNORECASE | re.DOTALL):
            old_style = style_match.group(0)
            css_text = style_match.group(2)
            new_css = rewrite_css_text(css_text, target_map)
            if new_css != css_text:
                new_style = style_match.group(1) + new_css + style_match.group(3)
                new_content = new_content.replace(old_style, new_style, 1)
        if new_content != content:
            xhtml_file.write_text(new_content, encoding="utf-8")
