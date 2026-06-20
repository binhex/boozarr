"""Chapter detection and ToC injection processor."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.processors.base import BaseProcessor, Fix, Issue

_CHAPTER_PATTERNS = [
    re.compile(r"Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"Part\s+\d+", re.IGNORECASE),
    re.compile(r"Section\s+\d+", re.IGNORECASE),
    re.compile(r"CHAPTER\s+\w+", re.IGNORECASE),
]
_NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"


class ChaptersProcessor(BaseProcessor):
    name = "chapters"

    @staticmethod
    def _find_ncx_path(epub: Any) -> str | None:
        """Locate the NCX file inside the EPUB."""
        try:
            epub.read_file("toc.ncx")
            return "toc.ncx"
        except Exception:
            pass
        try:
            opf_path = epub.get_opf_path()
            return ChaptersProcessor._search_opf_for_ncx(epub, opf_path)
        except Exception:
            pass
        return None

    @staticmethod
    def _search_opf_for_ncx(epub: Any, opf_path: str) -> str | None:
        """Read the OPF manifest and return the NCX href, or None."""
        opf_content = epub.read_file(opf_path)
        root = ElementTree.fromstring(opf_content)
        for item in root.iter():
            if not (item.tag.endswith("}item") or item.tag == "item"):
                continue
            mt = item.get("media-type", "")
            if "dtbncx" in mt or "ncx" in mt:
                return item.get("href")
            href = item.get("href", "")
            if href.endswith(".ncx"):
                return href
        return None

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        """Check if the EPUB has an NCX table of contents with entries."""
        ncx_path = self._find_ncx_path(epub)
        if ncx_path is None:
            return self._no_chapters_issue("toc.ncx")

        try:
            content = epub.read_file(ncx_path)
        except Exception:
            return self._no_chapters_issue(ncx_path)

        try:
            root = ElementTree.fromstring(content)
            if root.findall(f".//{{{_NCX_NS}}}navPoint"):
                return []
        except Exception:
            pass
        return self._no_chapters_issue(ncx_path)

    @staticmethod
    def _no_chapters_issue(location: str) -> list[Issue]:
        return [
            Issue(
                processor="chapters",
                severity="warn",
                location=location,
                description="No chapter entries found in table of contents",
                fix_possible=True,
            )
        ]

    @staticmethod
    def _discover_chapters(extract_dir: Path) -> list[tuple[str, str]]:
        """Scan XHTML files for chapter heading patterns and h1/h2 fallback."""
        discovered: list[tuple[str, str]] = []
        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
            if not xhtml_file.is_file():
                continue
            try:
                content = xhtml_file.read_text(encoding="utf-8")
            except Exception:
                continue
            rel_path = str(xhtml_file.relative_to(extract_dir))
            for pattern in _CHAPTER_PATTERNS:
                match = pattern.search(content)
                if match:
                    discovered.append((rel_path, match.group(0)))
                    break
            else:
                h_match = re.search(r"<h[12][^>]*>(.+?)</h[12]>", content, re.IGNORECASE)
                if h_match:
                    discovered.append((rel_path, h_match.group(1).strip()))
        return discovered

    @staticmethod
    def _write_ncx(ncx_path: Path, discovered: list[tuple[str, str]]) -> None:
        """Generate and write NCX XML content to the given path."""
        ncx_path.parent.mkdir(parents=True, exist_ok=True)
        ncx_parent = str(ncx_path.parent)
        items_xml = "\n".join(
            f'    <navPoint id="ch-{i}" playOrder="{i + 1}">'
            f"<navLabel><text>{escape(lab)}</text></navLabel>"
            f'<content src="{escape(os.path.relpath(p, ncx_parent))}"/>'
            f"</navPoint>"
            for i, (p, lab) in enumerate(discovered)
        )
        ncx_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" '
            '"http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
            f'<ncx xmlns="{_NCX_NS}" version="2005-1">\n'
            "  <head>\n"
            '    <meta name="dtb:uid" content="boozarr"/>\n'
            '    <meta name="dtb:depth" content="1"/>\n'
            '    <meta name="dtb:totalPageCount" content="0"/>\n'
            '    <meta name="dtb:maxPageNumber" content="0"/>\n'
            "  </head>\n"
            "  <docTitle><text>Chapters</text></docTitle>\n"
            f"  <navMap>\n{items_xml}\n  </navMap>\n"
            f"</ncx>\n"
        )
        ncx_path.write_text(ncx_content, encoding="utf-8")

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Generate an NCX file from XHTML headings and write it to the EPUB."""
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []

        discovered = self._discover_chapters(extract_dir)
        if not discovered:
            return []

        ncx_rel = "toc.ncx"
        for f in extract_dir.rglob("*.ncx"):
            ncx_rel = str(f.relative_to(extract_dir))

        ncx_path = extract_dir / ncx_rel
        self._write_ncx(ncx_path, discovered)

        return [
            Fix(
                self.name,
                ncx_rel,
                f"Added {len(discovered)} chapter entries to {ncx_rel}",
                old_value="",
                new_value=f"<navMap>{len(discovered)} entries</navMap>",
            )
        ]
