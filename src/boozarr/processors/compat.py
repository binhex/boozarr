"""Cross-device compatibility processor."""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from boozarr.processors.base import BaseProcessor, Fix, Issue

_FONT_MEDIA_TYPES: tuple[str, ...] = (
    "application/x-font-otf",
    "font/otf",
    "application/x-font-ttf",
    "font/ttf",
    "application/font-woff",
    "application/vnd.ms-fontobject",
)
# WOFF2 is intentionally excluded — required by EPUB3 readers.

_APPLE_DISPLAY_OPTIONS = "META-INF/com.apple.ibooks.display-options.xml"
_FONT_FACE_RE = re.compile(r"@font-face\s*\{[^}]*\}", re.IGNORECASE)


class CompatProcessor(BaseProcessor):
    name = "compat"

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        """Scan OPF manifest for embedded fonts and Apple Books display options."""
        if config is None or not config.get("normalise"):
            return []

        try:
            opf_path = epub.get_opf_path()
            opf_content = epub.read_file(opf_path)
            root = ElementTree.fromstring(opf_content)
        except Exception:
            return []

        issues: list[Issue] = []
        for item in root.iter():
            tag = item.tag.split("}")[-1] if "}" in item.tag else item.tag
            if tag != "item":
                continue
            CompatProcessor._scan_item(item, issues)

        # Detect namespace-prefixed OPF
        for elem in root.iter():
            if "}" in elem.tag:
                tag_uri, _, _ = elem.tag.partition("}")
                if tag_uri.startswith("{") and tag_uri[1:] == "http://www.idpf.org/2007/opf":
                    issues.append(
                        Issue(
                            processor="compat",
                            severity="info",
                            location="opf",
                            description="OPF uses namespace-prefixed tags",
                            fix_possible=True,
                        )
                    )
                    break

        return issues

    @staticmethod
    def _scan_item(item: Any, issues: list[Issue]) -> None:
        """Check a single manifest item for font or Apple-specific content."""
        mt = item.get("media-type", "")
        href = item.get("href", "")
        if mt in _FONT_MEDIA_TYPES:
            issues.append(
                Issue(
                    processor="compat",
                    severity="info",
                    location=f"font: {href}",
                    description=f"Embedded font found: {href}",
                    fix_possible=True,
                )
            )
        elif href == _APPLE_DISPLAY_OPTIONS or href.endswith("/" + _APPLE_DISPLAY_OPTIONS):
            issues.append(
                Issue(
                    processor="compat",
                    severity="info",
                    location=f"meta: {href}",
                    description="Apple Books display options found",
                    fix_possible=True,
                )
            )

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Remove embedded fonts, Apple metadata, normalise OPF namespace, clean CSS."""
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []

        fixes: list[Fix] = []
        removed_fonts: set[str] = set()

        try:
            opf_path = epub.get_opf_path()
            opf_file = extract_dir / opf_path
            opf_content = opf_file.read_text(encoding="utf-8")
        except Exception:
            return []

        for issue in issues:
            opf_content = CompatProcessor._process_fix_issue(
                issue, extract_dir, opf_path, opf_content, fixes, removed_fonts
            )

        if fixes:
            with contextlib.suppress(OSError):
                opf_file.write_text(opf_content, encoding="utf-8")

        # Normalise OPF namespace
        if self._normalise_opf_namespace(extract_dir, opf_path):
            fixes.append(
                Fix(
                    processor=self.name,
                    location=opf_path,
                    description="Normalised OPF namespace prefixes for cross-device compatibility",
                    old_value="namespace-prefixed",
                    new_value="bare-tag",
                )
            )

        # Clean up @font-face CSS rules
        self._strip_font_faces(extract_dir, removed_fonts)

        return fixes

    @staticmethod
    def _process_fix_issue(
        issue: Issue,
        extract_dir: Path,
        opf_path: str,
        opf_content: str,
        fixes: list[Fix],
        removed_fonts: set[str],
    ) -> str:
        """Process a single fix issue. Returns updated opf_content."""
        prefix, _, path = issue.location.partition(": ")

        if prefix == "font":
            removed_fonts.add(path)
            # Resolve href relative to OPF directory
            opf_dir = str(Path(opf_path).parent)
            resolved = str(Path(opf_dir) / path) if opf_dir != "." else path
            font_file = extract_dir / resolved
            try:
                font_file.unlink(missing_ok=True)
            except OSError:
                return opf_content
            opf_content = CompatProcessor._remove_manifest_item(opf_content, path)
            fixes.append(
                Fix(
                    processor="compat",
                    location=issue.location,
                    description=f"Removed embedded font: {path}",
                    old_value=path,
                    new_value="",
                )
            )
            return opf_content

        if prefix == "meta" and "apple" in issue.description.lower():
            ado_file = extract_dir / path
            try:
                ado_file.unlink(missing_ok=True)
            except OSError:
                return opf_content
            opf_content = CompatProcessor._remove_manifest_item(opf_content, path)
            fixes.append(
                Fix(
                    processor="compat",
                    location=issue.location,
                    description="Removed Apple Books display options",
                    old_value=path,
                    new_value="",
                )
            )
            return opf_content

        return opf_content

    @staticmethod
    def _collect_other_namespaces(root: Any) -> list[tuple[str, str]]:
        """Collect namespace prefix/URI pairs from the root element, excluding OPF."""
        opf_ns = "http://www.idpf.org/2007/opf"
        result: list[tuple[str, str]] = []
        for key, value in root.attrib.items():
            if key.startswith("xmlns:") and value != opf_ns:
                prefix = key.split(":", 1)[1]
                result.append((prefix, value))
        return result

    @staticmethod
    def _remove_manifest_item(opf_xml: str, href: str) -> str:
        """Remove <item> elements whose href matches from the OPF manifest."""
        escaped = re.escape(href)
        return re.sub(
            r'<(?:\w+:)?item\b[^>]*href="' + escaped + r'"[^>]*/?>\s*',
            "",
            opf_xml,
            count=1,
        )

    @staticmethod
    def _normalise_opf_namespace(extract_dir: Path, opf_path: str) -> bool:
        """Rewrite OPF namespace prefix to default form. Preserves DC namespace.

        Returns True if the OPF was modified.
        """
        opf_file = extract_dir / opf_path
        try:
            tree = ElementTree.parse(str(opf_file))
        except Exception:
            return False

        opf_ns = "http://www.idpf.org/2007/opf"
        changed = False

        for elem in tree.iter():
            tag_uri, _, tag_local = elem.tag.partition("}")
            if tag_uri and tag_uri.startswith("{") and tag_uri[1:] == opf_ns:
                elem.tag = tag_local
                changed = True
            if hasattr(elem, "attrib"):
                new_attrib: dict[str, str] = {}
                for k, v in elem.attrib.items():
                    ns_uri, _, local = k.partition("}")
                    if ns_uri and ns_uri.startswith("{") and ns_uri[1:] == opf_ns:
                        new_attrib[local] = v
                        changed = True
                    else:
                        new_attrib[k] = v
                elem.attrib = new_attrib

        if changed:
            root = tree.getroot()
            root.set("xmlns", opf_ns)
            ElementTree.register_namespace("", opf_ns)
            for prefix, uri in CompatProcessor._collect_other_namespaces(root):
                ElementTree.register_namespace(prefix, uri)
            with contextlib.suppress(OSError):
                tree.write(str(opf_file), xml_declaration=True, encoding="unicode")

        return changed

    @staticmethod
    def _strip_font_faces(extract_dir: Path, removed_hrefs: set[str]) -> None:
        """Remove @font-face blocks that reference stripped font files from all CSS files."""
        if not removed_hrefs:
            return
        for css_file in extract_dir.rglob("*.css"):
            try:
                content = css_file.read_text(encoding="utf-8")
            except Exception:
                continue
            new_content = content
            for match in _FONT_FACE_RE.finditer(content):
                block = match.group(0)
                if any(href in block for href in removed_hrefs):
                    new_content = new_content.replace(block, "", 1)
            if new_content != content:
                with contextlib.suppress(OSError):
                    css_file.write_text(new_content, encoding="utf-8")
