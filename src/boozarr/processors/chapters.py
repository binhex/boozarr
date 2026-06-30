"""Chapter detection and ToC injection processor."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from boozarr.processors.base import BaseProcessor, Fix, Issue

_CHAPTER_PATTERNS = [
    re.compile(r"Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"Part\s+\d+", re.IGNORECASE),
    re.compile(r"Section\s+\d+", re.IGNORECASE),
    re.compile(r"CHAPTER\s+\w+", re.IGNORECASE),
]
_SKIP_FILENAME_SUBSTRINGS: tuple[str, ...] = (
    "cover",
    "title",
    "toc",
    "nav",
    "copyright",
    "about",
)


def _should_skip_content_file(stem_lower: str) -> bool:
    """True if the filename stem indicates non-content (cover, title, toc, etc.).

    Matches when a skip-word appears as a whole component separated by ``_``
    or ``-``, or as the entire stem.  This avoids false positives like
    ``"subtitle"`` or ``"navigation"`` while catching ``"title_page"``.
    """
    words = set(stem_lower.replace("-", "_").split("_"))
    return bool(words & set(_SKIP_FILENAME_SUBSTRINGS))


_SMALL_FILE_THRESHOLD: int = 2048
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
        """Read the OPF manifest and return the resolved NCX path, or None.

        The NCX href in the OPF manifest is relative to the OPF file's
        directory.  This method resolves it to a path relative to the EPUB
        root so the caller can read the file without further path mangling.
        """
        opf_content = epub.read_file(opf_path)
        root = ElementTree.fromstring(opf_content)
        opf_dir = str(Path(opf_path).parent)
        for item in root.iter():
            if not (item.tag.endswith("}item") or item.tag == "item"):
                continue
            href = ChaptersProcessor._get_ncx_href(item)
            if href is not None:
                return str(Path(opf_dir) / href) if opf_dir != "." else href
        return None

    @staticmethod
    def _get_ncx_href(item: Any) -> str | None:
        """Return the href from an OPF manifest item if it references an NCX."""
        mt: str = item.get("media-type", "")
        if "dtbncx" in mt or "ncx" in mt:
            href: str | None = item.get("href")
            return href
        candidate: str = item.get("href", "")
        return candidate if candidate.endswith(".ncx") else None

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
                processor=ChaptersProcessor.name,
                severity="warn",
                location=location,
                description="No chapter entries found in table of contents",
                fix_possible=True,
            )
        ]

    @staticmethod
    def _label_from_filename(stem: str) -> str:
        """Extract a human-readable chapter label from a filename stem.

        Trailing digits become 'Chapter N' (stripping leading zeros).
        Stems without digits are cleaned up (underscores -> spaces, title-cased).
        """
        match = re.search(r"(\d+)$", stem)
        if match:
            num: int = int(match.group(1))
            return f"Chapter {num}"
        label: str = stem.replace("_", " ").strip()
        if label:
            label = label[0].upper() + label[1:]
        return label if label else "Chapter"

    @staticmethod
    def _resolve_spine_order(extract_dir: Path, opf_path: str) -> dict[str, int]:
        """Parse OPF spine to get file reading order.

        Returns:
            Mapping from file path (relative to extract_dir) to zero-based spine
            position.  Empty dict on parse failure or missing spine.
        """
        opf_file = extract_dir / opf_path
        try:
            root = ElementTree.parse(str(opf_file)).getroot()
        except Exception:
            return {}

        manifest = ChaptersProcessor._parse_opf_manifest(root)
        namespace = ChaptersProcessor._detect_xml_namespace(root)
        opf_dir = str(Path(opf_path).parent)

        return ChaptersProcessor._collect_spine_order(root, manifest, opf_dir, namespace)

    @staticmethod
    def _parse_opf_manifest(root: Any) -> dict[str, str]:
        """Build {id: href} from OPF manifest items."""
        manifest: dict[str, str] = {}
        for element in root.iter():
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
            if tag == "item":
                item_id = element.get("id")
                href = element.get("href")
                if item_id and href:
                    manifest[item_id] = href
        return manifest

    @staticmethod
    def _detect_xml_namespace(root: Any) -> str:
        """Extract XML namespace from the first namespaced element."""
        for element in root.iter():
            if "}" in element.tag:
                tag_str: str = element.tag
                ns: str = "{" + tag_str.split("}")[0][1:] + "}"
                return ns
        return ""

    @staticmethod
    def _collect_spine_order(root: Any, manifest: dict[str, str], opf_dir: str, namespace: str) -> dict[str, int]:
        """Collect spine items, trying namespace-aware then local-tag matching."""
        order: dict[str, int] = {}

        for element in root.iter(f"{namespace}spine"):
            for itemref in element:
                ChaptersProcessor._add_spine_item(order, itemref.get("idref"), manifest, opf_dir)

        if not order:
            for element in root.iter():
                tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
                if tag == "itemref":
                    ChaptersProcessor._add_spine_item(order, element.get("idref"), manifest, opf_dir)

        return order

    @staticmethod
    def _add_spine_item(order: dict[str, int], idref: str | None, manifest: dict[str, str], opf_dir: str) -> None:
        """Resolve a single spine itemref and add it to the order dict."""
        if idref and idref in manifest:
            href = manifest[idref]
            resolved = str(Path(opf_dir) / href) if opf_dir != "." else href
            if resolved not in order:
                order[resolved] = len(order)

    @staticmethod
    def _discover_from_spine(extract_dir: Path, opf_path: str) -> list[tuple[str, str]]:
        """Generate chapter entries from the OPF spine reading order.

        Only called when _discover_chapters finds zero text-pattern matches.
        Filters out non-content files via smart heuristics and labels each
        remaining file by extracting trailing digits from its stem.
        """
        order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)
        if not order:
            return []

        discovered: list[tuple[str, str]] = []
        for file_path in order:
            full_path = extract_dir / file_path
            if not full_path.is_file():
                continue

            stem = full_path.stem.lower()
            if _should_skip_content_file(stem):
                continue

            try:
                if full_path.stat().st_size < _SMALL_FILE_THRESHOLD:
                    continue
            except OSError:
                continue

            label = ChaptersProcessor._label_from_filename(full_path.stem)
            discovered.append((file_path, label))

        return discovered

    @staticmethod
    def _discover_chapters(extract_dir: Path, opf_path: str | None = None) -> list[tuple[str, str]]:
        """Scan XHTML files for chapter patterns and h1/h2 fallback.

        Returns all matches across all pattern types, deduplicated by
        (file_path, byte_offset).  Sorted by spine order when opf_path
        is provided, otherwise by file path alphabetically.
        """
        discovered: list[tuple[str, str]] = []
        seen: set[tuple[str, int]] = set()

        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
            if xhtml_file.is_file():
                ChaptersProcessor._scan_file_for_chapters(xhtml_file, extract_dir, discovered, seen)

        if opf_path is not None and discovered:
            return _sort_by_spine_order(discovered, extract_dir, opf_path)
        return discovered

    @staticmethod
    def _scan_file_for_chapters(
        xhtml_file: Path,
        extract_dir: Path,
        discovered: list[tuple[str, str]],
        seen: set[tuple[str, int]],
    ) -> None:
        """Scan one XHTML file for chapter patterns; fall back to h1/h2."""
        try:
            content = xhtml_file.read_text(encoding="utf-8")
        except Exception:
            return
        rel_path = str(xhtml_file.relative_to(extract_dir))

        matched = False
        for pattern in _CHAPTER_PATTERNS:
            for match in pattern.finditer(content):
                pos = match.start()
                if (rel_path, pos) not in seen:
                    discovered.append((rel_path, match.group(0)))
                    seen.add((rel_path, pos))
                matched = True

        if not matched:
            h_match = re.search(r"<h[12][^>]*>(.+?)</h[12]>", content, re.IGNORECASE)
            if h_match:
                discovered.append((rel_path, h_match.group(1).strip()))

    @staticmethod
    def _write_ncx(ncx_path: Path, discovered: list[tuple[str, str]], extract_dir: Path) -> None:
        """Generate and write NCX XML content to the given path.

        The *discovered* paths are relative to *extract_dir*.  When
        *extract_dir* is provided the paths are resolved to absolute before
        computing the relative path from the NCX directory — this avoids
        ``os.path.relpath`` misinterpreting relative paths against CWD.
        """
        ncx_path.parent.mkdir(parents=True, exist_ok=True)
        ncx_parent = str(ncx_path.parent)
        items_xml = "\n".join(
            f'    <navPoint id="ch-{i}" playOrder="{i + 1}">'
            f"<navLabel><text>{escape(lab)}</text></navLabel>"
            f'<content src="{escape(os.path.relpath(str(extract_dir / p), ncx_parent))}"/>'
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

    @staticmethod
    def _get_opf_path_safe(epub: Any) -> str | None:
        """Return the OPF path, or None on failure."""
        try:
            result: str | None = epub.get_opf_path()
            return result
        except Exception:
            return None

    @staticmethod
    def _find_ncx_rel(extract_dir: Path) -> str:
        """Find the NCX filename relative to extract_dir."""
        for f in extract_dir.rglob("*.ncx"):
            return str(f.relative_to(extract_dir))
        return "toc.ncx"

    @staticmethod
    def _discover_all_chapters(extract_dir: Path, opf_path: str | None) -> list[tuple[str, str]]:
        """Discover chapters via patterns, falling back to spine when empty."""
        discovered = ChaptersProcessor._discover_chapters(extract_dir, opf_path)
        if not discovered and opf_path is not None:
            discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)
        return discovered

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Generate an NCX file from XHTML headings and write it to the EPUB."""
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []

        discovered = self._discover_all_chapters(extract_dir, self._get_opf_path_safe(epub))
        if not discovered:
            return []

        ncx_rel = self._find_ncx_rel(extract_dir)
        self._write_ncx(extract_dir / ncx_rel, discovered, extract_dir)

        return [
            Fix(
                self.name,
                ncx_rel,
                f"Added {len(discovered)} chapter entries to {ncx_rel}",
                old_value="",
                new_value=f"<navMap>{len(discovered)} entries</navMap>",
            )
        ]


def _sort_by_spine_order(discovered: list[tuple[str, str]], extract_dir: Path, opf_path: str) -> list[tuple[str, str]]:
    """Sort discovered entries by OPF spine reading order."""
    order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)
    if not order:
        return discovered

    def _key(item: tuple[str, str]) -> tuple[int, str]:
        return (order.get(item[0], 999_999), item[0])

    return sorted(discovered, key=_key)
