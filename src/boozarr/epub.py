"""EPUB file wrapper — validate, extract, modify, repack."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


class EpubWrapper:
    """Wraps a single EPUB file on disk.

    Provides validation, extraction to a temp directory, file-level
    read/write access, and re-packing into a compressed ZIP archive.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        if not path.exists():
            raise FileNotFoundError(f"EPUB not found: {path}")
        self.file_hash: str = self._compute_hash(path)
        self._extract_dir: Path | None = None

    @staticmethod
    def _compute_hash(path: Path) -> str:
        """Compute SHA-256 using streaming reads to avoid loading large files into memory."""
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def validate(self) -> None:
        """Verify the file is a valid ZIP with EPUB structure."""
        if not zipfile.is_zipfile(self.path):
            raise zipfile.BadZipFile(f"Not a valid ZIP file: {self.path}")
        with zipfile.ZipFile(self.path, "r") as zf:
            names = zf.namelist()
        if not any("META-INF/container.xml" in n for n in names):
            raise ValueError(f"Missing EPUB structure (META-INF/container.xml) in {self.path}")
        if not any(n.endswith(".opf") for n in names):
            raise ValueError(f"Missing EPUB structure (.opf file) in {self.path}")

    def extract(self, target_dir: Path) -> None:
        """Extract the EPUB ZIP into *target_dir*.

        Validates each entry path to defend against zip-slip path traversal
        attacks via malicious ZIP entries containing ``../``.
        """
        self._extract_dir = target_dir
        with zipfile.ZipFile(self.path, "r") as zf:
            target_str = str(target_dir.resolve())
            for member in zf.infolist():
                member_path = str(Path(target_str, member.filename).resolve())
                if not member_path.startswith(target_str + "/"):
                    raise ValueError(f"ZIP entry '{member.filename}' attempts path traversal")
                zf.extract(member, target_dir)

    def read_file(self, relative_path: str) -> str:
        """Read a file from the EPUB: from extracted dir if present, else from the ZIP."""
        if self._extract_dir is not None:
            fpath = (self._extract_dir / relative_path).resolve()
            if not str(fpath).startswith(str(self._extract_dir.resolve()) + "/"):
                raise ValueError(f"Path traversal detected: {relative_path}")
            return fpath.read_text(encoding="utf-8")
        with zipfile.ZipFile(self.path, "r") as zf:
            return zf.read(relative_path).decode("utf-8")

    def get_opf_path(self) -> str:
        """Read META-INF/container.xml and return the OPF file path."""
        import xml.etree.ElementTree as ET

        container = ET.fromstring(self.read_file("META-INF/container.xml"))
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfile = container.find(".//c:rootfile", ns)
        if rootfile is not None:
            return rootfile.get("full-path", "OEBPS/content.opf")
        return "OEBPS/content.opf"

    def write_file(self, file_path: Path, content: str) -> None:
        """Write *content* to a file relative to the extracted tree."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def repack(self, output_path: Path) -> None:
        """Re-zip the extracted directory into *output_path* with deflate compression."""
        if self._extract_dir is None or not self._extract_dir.exists():
            raise RuntimeError("No extracted directory to repack. Call extract() first.")
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in sorted(self._extract_dir.rglob("*")):
                if fpath.is_file():
                    zf.write(fpath, str(fpath.relative_to(self._extract_dir)))

    def refresh_hash(self) -> None:
        """Recompute the SHA-256 hash from the current file on disk.

        Call after repack() to keep the hash in sync with the modified file.
        """
        self.file_hash = self._compute_hash(self.path)
