"""Missing metadata fixer processor."""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from boozarr.processors.base import BaseProcessor, Fix, Issue

_OPF_METADATA_NS = "http://purl.org/dc/elements/1.1/"
_REQUIRED = ["dc:title", "dc:creator", "dc:language", "dc:date"]


class MetadataProcessor(BaseProcessor):
    name = "metadata"

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        """Read the OPF and report missing dc: metadata elements."""
        opf_path = epub.get_opf_path() if hasattr(epub, "get_opf_path") else "OEBPS/content.opf"
        try:
            opf_content = epub.read_file(opf_path)
        except Exception as exc:
            return [Issue(self.name, "error", opf_path, f"Cannot read OPF file: {exc}", fix_possible=False)]

        root = ElementTree.fromstring(opf_content)
        issues: list[Issue] = []
        for field in _REQUIRED:
            tag = f"{{{_OPF_METADATA_NS}}}{field.split(':')[1]}"
            if root.find(f".//{tag}") is None:
                issues.append(
                    Issue(
                        processor=self.name,
                        severity="warn",
                        location=opf_path,
                        description=f"Missing {field}",
                        fix_possible=True,
                    )
                )
        return issues

    @staticmethod
    def _parse_filename(epub: Any) -> tuple[str, str]:
        """Extract author and title from the EPUB filename.

        Supports ``Author - Title.epub`` convention. Falls back to
        stem when no hyphen pattern matches.
        """
        filename = getattr(epub, "path", None)
        fname = str(filename) if filename else ""
        match = re.match(r"(.+?)\s*-\s*(.+?)\.epub", fname.rsplit("/", 1)[-1], re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return "Unknown Author", Path(fname).stem if fname else "Unknown Title"

    @staticmethod
    def _build_values(issues: list[Issue], author: str, title: str) -> dict[str, str]:
        """Build a dict of metadata field -> value from the issues list."""
        values: dict[str, str] = {}
        for issue in issues:
            desc = issue.description or ""
            field = desc.replace("Missing ", "", 1) if desc.startswith("Missing ") else ""
            if field == "dc:title":
                values["dc:title"] = title
            elif field == "dc:creator":
                values["dc:creator"] = author
            elif field == "dc:language":
                values["dc:language"] = "en"
            elif field == "dc:date":
                values["dc:date"] = datetime.date.today().isoformat()
        return values

    @staticmethod
    def _write_opf(opf_path: Path, values: dict[str, str]) -> bool:
        """Write missing metadata elements into the OPF file. Returns True on success."""
        try:
            tree = ElementTree.parse(opf_path)
        except Exception:
            return False

        root = tree.getroot()
        meta = MetadataProcessor._find_metadata(root)
        if meta is None:
            meta = ElementTree.SubElement(root, "{http://www.idpf.org/2007/opf}metadata")

        ns_dc = _OPF_METADATA_NS
        for field, value in values.items():
            tag = f"{{{ns_dc}}}{field.split(':')[1]}"
            if meta.find(f".//{tag}") is None:
                elem = ElementTree.SubElement(meta, tag)
                elem.text = value

        tree.write(opf_path, xml_declaration=True, encoding="utf-8")
        return True

    @staticmethod
    def _find_metadata(root: ElementTree.Element) -> ElementTree.Element | None:
        """Find the first <metadata> child element regardless of namespace."""
        for child in root:
            if child.tag.endswith("}metadata") or child.tag == "metadata":
                return child
        return None

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        """Infer missing metadata and write it into the OPF file."""
        author, title = self._parse_filename(epub)
        values = self._build_values(issues, author, title)

        if not values:
            return []

        opf_rel = epub.get_opf_path() if hasattr(epub, "get_opf_path") else "OEBPS/content.opf"
        extract_dir = getattr(epub, "_extract_dir", None)
        if extract_dir is None:
            return []

        opf_path = extract_dir / opf_rel
        if not self._write_opf(opf_path, values):
            return []

        today = datetime.date.today().isoformat()
        return [
            Fix(
                self.name,
                opf_rel,
                f"Defaulted date to {today}" if spec["field"] == "dc:date" else spec["desc"],
                "",
                spec["value"],
            )
            for spec in [
                {"field": "dc:title", "desc": f"Inferred title '{title}'", "value": title},
                {"field": "dc:creator", "desc": f"Inferred author '{author}'", "value": author},
                {"field": "dc:language", "desc": "Defaulted language to 'en'", "value": "en"},
                {"field": "dc:date", "desc": f"Defaulted date to {today}", "value": today},
            ]
            if spec["field"] in values
        ]
