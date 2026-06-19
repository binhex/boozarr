# Boozarr EPUB Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working CLI tool that batch-processes EPUB files — running checks and fixes for chapters, borders, metadata, CSS, links, and compression.

**Architecture:** Single-process pipeline architecture. A Click CLI parses options, instantiates a Pipeline with user-selected processors, then iterates over EPUB files in a library directory. Each EPUB is extracted to a temp dir, inspected/manipulated via EpubWrapper, then repacked. An SQLite DB tracks processed files by SHA-256 to skip unchanged files on re-run.

**Tech Stack:** Python 3.12+, Click (CLI), Loguru (logging), ebooklib (EPUB OPF/NCX), lxml (XHTML/XML parsing), tinycss2 (CSS parsing), sqlite3 (stdlib), pytest (testing).

**Default paths:** Logs at `<project_root>/logs/boozarr.log`, DB at `<project_root>/db/boozarr.db`.

---

### Task 1: EpubWrapper — EPUB file handling core

**Files:**
- Create: `src/boozarr/epub.py`
- Test: `tests/test_epub.py`

**Responsibility:** Wrap an EPUB file (ZIP archive) — validate, extract to temp dir, provide access to internal files, repack. Foundation for all processors.

- [ ] **Step 1: Write failing tests for EpubWrapper**

Create `tests/test_epub.py`:

```python
"""Tests for EpubWrapper — EPUB file handling."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from boozarr.epub import EpubWrapper


class TestEpubWrapperInit:
    def test_init_computes_sha256(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_bytes(b"fake epub content")
        wrapper = EpubWrapper(epub_path)
        expected = hashlib.sha256(b"fake epub content").hexdigest()
        assert wrapper.file_hash == expected
        assert wrapper.path == epub_path

    def test_init_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            EpubWrapper(Path("/nonexistent.epub"))


class TestEpubWrapperValidation:
    def test_validate_valid_zip(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "valid.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
        epub_path.write_bytes(epub_path.read_bytes())  # flush
        wrapper = EpubWrapper(epub_path)
        wrapper.validate()  # should not raise

    def test_validate_not_a_zip(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "notazip.epub"
        epub_path.write_bytes(b"not a zip file")
        wrapper = EpubWrapper(epub_path)
        with pytest.raises(zipfile.BadZipFile):
            wrapper.validate()


class TestEpubWrapperRepack:
    def test_repack_preserves_content(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "input.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr("OEBPS/chapter1.xhtml", "<html><body><p>Hello</p></body></html>")
        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        assert (extract_dir / "OEBPS/chapter1.xhtml").read_text() == "<html><body><p>Hello</p></body></html>"
        wrapper.write_file(extract_dir / "OEBPS/chapter1.xhtml", "<html><body><p>Modified</p></body></html>")
        output_path = tmp_path / "output.epub"
        wrapper.repack(output_path)
        with zipfile.ZipFile(output_path, "r") as zf:
            assert zf.read("OEBPS/chapter1.xhtml").decode() == "<html><body><p>Modified</p></body></html>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_epub.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'boozarr.epub'`

- [ ] **Step 3: Write EpubWrapper implementation**

Write `src/boozarr/epub.py`:

```python
"""EPUB file wrapper — validate, extract, inspect, repack."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


class EpubWrapper:
    """Represents a single EPUB file on disk.

    Provides validation, extraction to temp directory, file-level read/write
    access to the extracted tree, and re-packing into a ZIP.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        if not path.exists():
            raise FileNotFoundError(f"EPUB not found: {path}")
        self.file_hash: str = hashlib.sha256(path.read_bytes()).hexdigest()
        self._extract_dir: Path | None = None

    def validate(self) -> None:
        """Verify the file is a valid ZIP and contains basic EPUB structure."""
        if not zipfile.is_zipfile(self.path):
            raise zipfile.BadZipFile(f"Not a valid ZIP file: {self.path}")
        with zipfile.ZipFile(self.path, "r") as zf:
            names = zf.namelist()
        has_container = any("META-INF/container.xml" in n for n in names)
        has_opf = any(n.endswith(".opf") for n in names)
        if not has_container or not has_opf:
            raise ValueError(f"Missing EPUB structure in {self.path}")

    def extract(self, target_dir: Path) -> None:
        """Extract the EPUB ZIP into *target_dir*."""
        self._extract_dir = target_dir
        with zipfile.ZipFile(self.path, "r") as zf:
            zf.extractall(target_dir)

    def write_file(self, file_path: Path, content: str) -> None:
        """Write *content* to a file inside the extracted tree."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def repack(self, output_path: Path) -> None:
        """Re-zip the extracted directory into *output_path* with compression."""
        if self._extract_dir is None or not self._extract_dir.exists():
            raise RuntimeError("No extracted directory to repack. Call extract() first.")
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in sorted(self._extract_dir.rglob("*")):
                if fpath.is_file():
                    arcname = str(fpath.relative_to(self._extract_dir))
                    zf.write(fpath, arcname)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_epub.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/epub.py tests/test_epub.py
git commit -m "feat: add EpubWrapper for EPUB file handling"
```

---

### Task 2: SQLite Database — processing tracking

**Files:**
- Create: `src/boozarr/db.py`
- Test: `tests/test_db.py`

**Responsibility:** SQLite DB tracking processed files by SHA-256. Provides init (create tables), lookup (hash → skip), record (insert/update), and log (append events).

- [ ] **Step 1: Write failing tests for ProcessingDB**

Create `tests/test_db.py`:

```python
"""Tests for ProcessingDB — SQLite tracking database."""

from __future__ import annotations

from pathlib import Path

import pytest

from boozarr.db import ProcessingDB


class TestProcessingDBInit:
    def test_init_creates_tables(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        cursor = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "processed_files" in tables
        assert "processing_log" in tables

    def test_init_reuses_existing_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db1 = ProcessingDB(db_path)
        db1.record_file("a.epub", "hash1", "ok", issues=0, fixes=0, dry_run=True)
        db1.close()
        db2 = ProcessingDB(db_path)
        assert db2.lookup_hash("hash1") == "ok"
        db2.close()


class TestProcessingDBLookup:
    def test_lookup_missing_hash(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        assert db.lookup_hash("nonexistent") is None

    def test_lookup_existing_hash(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        db.record_file("a.epub", "abc123", "ok", issues=2, fixes=1, dry_run=True)
        assert db.lookup_hash("abc123") == "ok"


class TestProcessingDBRecord:
    def test_record_and_log(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        db.record_file("book.epub", "def456", "ok", issues=0, fixes=3, dry_run=False)
        cursor = db.conn.execute("SELECT file_path, status, fixes_applied FROM processed_files")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "book.epub"
        assert row[1] == "ok"
        assert row[2] == 3

    def test_log_processing_event(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        db.log_event("book.epub", "chapters", "check", '{"found": 0}')
        cursor = db.conn.execute("SELECT file_path, processor, action FROM processing_log")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "book.epub"
        assert row[1] == "chapters"
        assert row[2] == "check"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'boozarr.db'`

- [ ] **Step 3: Write ProcessingDB implementation**

Create `src/boozarr/db.py`:

```python
"""SQLite database for tracking processed EPUB files."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS processed_files (
    file_path TEXT PRIMARY KEY,
    file_hash TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    issues_found INTEGER DEFAULT 0,
    fixes_applied INTEGER DEFAULT 0,
    dry_run BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    processor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT,
    timestamp TEXT NOT NULL
);
"""


class ProcessingDB:
    """Thread-unsafe SQLite wrapper for the boozarr tracking database."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def lookup_hash(self, file_hash: str) -> str | None:
        cursor = self.conn.execute(
            "SELECT status FROM processed_files WHERE file_hash = ?", (file_hash,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def record_file(
        self, file_path: str, file_hash: str, status: str,
        issues: int, fixes: int, dry_run: bool,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO processed_files
               (file_path, file_hash, processed_at, status, issues_found, fixes_applied, dry_run)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (file_path, file_hash, now, status, issues, fixes, dry_run),
        )
        self.conn.commit()

    def log_event(self, file_path: str, processor: str, action: str, detail: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO processing_log (file_path, processor, action, detail, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (file_path, processor, action, detail, now),
        )
        self.conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/db.py tests/test_db.py
git commit -m "feat: add ProcessingDB for tracking processed files"
```

---

### Task 3: Issue/Fix models, Report, and Processor base class

**Files:**
- Create: `src/boozarr/report.py`
- Create: `src/boozarr/processors/__init__.py`
- Create: `src/boozarr/processors/base.py`
- Test: `tests/test_report.py`
- Test: `tests/test_processor_base.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_report.py`:

```python
"""Tests for Report formatter."""

from __future__ import annotations

from boozarr.report import Report


class TestReport:
    def test_log_line_ok(self) -> None:
        r = Report()
        line = r.log_line("/path/book.epub", "ok", issues=0, fixes=3)
        assert "[OK]" in line
        assert "book.epub" in line

    def test_log_line_warn(self) -> None:
        r = Report()
        line = r.log_line("/path/book.epub", "warn", issues=2, fixes=0)
        assert "[WARN]" in line

    def test_log_line_err(self) -> None:
        r = Report()
        line = r.log_line("/path/book.epub", "error", issues=0, fixes=0)
        assert "[ERR]" in line

    def test_log_line_skip(self) -> None:
        r = Report()
        line = r.log_line("/path/book.epub", "skip", issues=0, fixes=0)
        assert "[SKIP]" in line

    def test_final_summary_counts(self) -> None:
        r = Report()
        r.log_line("a.epub", "ok", issues=0, fixes=3)
        r.log_line("b.epub", "warn", issues=2, fixes=0)
        r.log_line("c.epub", "error", issues=0, fixes=0)
        r.log_line("d.epub", "skip", issues=0, fixes=0)
        summary = r.final_summary(duration_s=12.4)
        assert "Processed: 4" in summary
        assert "Issues found: 2" in summary
        assert "Fixes applied: 3" in summary
        assert "Errors: 1" in summary
```

Create `tests/test_processor_base.py`:

```python
"""Tests for BaseProcessor abstract class."""

from __future__ import annotations

import pytest

from boozarr.processors.base import BaseProcessor, Issue, Fix


class TestIssueFixModels:
    def test_issue_creation(self) -> None:
        issue = Issue(
            processor="chapters", severity="warn",
            location="OEBPS/content.opf",
            description="No chapter markers found", fix_possible=True,
        )
        assert issue.processor == "chapters"
        assert issue.fix_possible is True

    def test_fix_creation(self) -> None:
        fix = Fix(
            processor="chapters", location="toc.ncx",
            description="Added 5 chapter entries",
            old_value="", new_value="<navMap>...</navMap>",
        )
        assert fix.processor == "chapters"
        assert fix.old_value == ""


class TestBaseProcessor:
    def test_cannot_instantiate_base(self) -> None:
        with pytest.raises(TypeError):
            BaseProcessor()  # type: ignore[abstract]

    def test_concrete_processor_works(self) -> None:
        class DummyProcessor(BaseProcessor):
            name = "dummy"
            def check(self, epub):  # type: ignore[no-untyped-def]
                return []
            def fix(self, epub, issues, config):  # type: ignore[no-untyped-def]
                return []
        p = DummyProcessor()
        assert p.name == "dummy"
        assert p.check(None) == []
        assert p.fix(None, [], {}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_report.py tests/test_processor_base.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Write implementations**

Create `src/boozarr/report.py`:

```python
"""Console summary reporting for boozarr processing runs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Report:
    """Accumulates per-file results and produces a final summary."""

    total: int = 0
    skipped: int = 0
    errors: int = 0
    total_issues: int = 0
    total_fixes: int = 0
    _lines: list[str] = field(default_factory=list, repr=False)

    def log_line(self, file_path: str, status: str, issues: int = 0, fixes: int = 0) -> str:
        self.total += 1
        self.total_issues += issues
        self.total_fixes += fixes
        filename = file_path.rsplit("/", 1)[-1]
        if status == "ok":
            tag = "[OK]"
        elif status == "warn":
            tag = "[WARN]"
        elif status == "error":
            tag = "[ERR]"
            self.errors += 1
        else:
            tag = "[SKIP]"
            self.skipped += 1
        line = f"{tag:8} {filename:50} — {issues} issues, {fixes} fixes"
        self._lines.append(line)
        return line

    def final_summary(self, duration_s: float) -> str:
        return (
            f"Processed: {self.total} files\n"
            f"  - Unchanged (skipped): {self.skipped}\n"
            f"  - Issues found: {self.total_issues}"
            f" across {self.total - self.skipped - self.errors} files\n"
            f"  - Fixes applied: {self.total_fixes}\n"
            f"  - Errors: {self.errors}\n"
            f"Duration: {duration_s:.1f}s"
        )
```

Create `src/boozarr/processors/__init__.py` (empty — just docstring):

```python
"""EPUB processor implementations for boozarr."""
```

Create `src/boozarr/processors/base.py`:

```python
"""Base processor abstract class and data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Issue:
    processor: str
    severity: str
    location: str
    description: str
    fix_possible: bool = True


@dataclass
class Fix:
    processor: str
    location: str
    description: str
    old_value: str = ""
    new_value: str = ""


class BaseProcessor(ABC):
    name: str = ""

    @abstractmethod
    def check(self, epub: Any) -> list[Issue]:
        ...

    @abstractmethod
    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_report.py tests/test_processor_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/report.py src/boozarr/processors/ tests/test_report.py tests/test_processor_base.py
git commit -m "feat: add Report, Issue/Fix models, BaseProcessor"
```

---

### Task 4: Pipeline orchestrator

**Files:**
- Create: `src/boozarr/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pipeline.py`:

```python
"""Tests for Pipeline orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from boozarr.pipeline import Pipeline


class TestPipeline:
    def test_process_epub_without_fix(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("dummy")
        db = MagicMock()
        db.lookup_hash.return_value = None
        processor = MagicMock()
        processor.name = "dummy"
        processor.check.return_value = []
        processor.fix.return_value = []
        pipeline = Pipeline(db=db, processors=[processor], config={}, fix=False)
        result = pipeline.process_epub(epub_path)
        assert result["file_path"] == str(epub_path)
        assert result["issues"] == 0
        assert result["fixes"] == 0
        processor.check.assert_called_once()
        processor.fix.assert_not_called()

    def test_process_epub_with_fix(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("dummy")
        db = MagicMock()
        db.lookup_hash.return_value = None
        processor = MagicMock()
        processor.name = "dummy"
        processor.check.return_value = []
        processor.fix.return_value = []
        pipeline = Pipeline(db=db, processors=[processor], config={}, fix=True)
        result = pipeline.process_epub(epub_path)
        assert result["issues"] == 0
        assert result["fixes"] == 0
        processor.check.assert_called_once()
        processor.fix.assert_called_once()

    def test_skips_already_processed_file(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("dummy")
        db = MagicMock()
        db.lookup_hash.return_value = "ok"
        processor = MagicMock()
        pipeline = Pipeline(db=db, processors=[processor], config={}, fix=False)
        result = pipeline.process_epub(epub_path)
        assert result["status"] == "skip"
        processor.check.assert_not_called()

    def test_catches_processor_error(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("dummy")
        db = MagicMock()
        db.lookup_hash.return_value = None
        processor = MagicMock()
        processor.name = "broken"
        processor.check.side_effect = RuntimeError("oops")
        pipeline = Pipeline(db=db, processors=[processor], config={}, fix=False)
        result = pipeline.process_epub(epub_path)
        assert result["status"] == "error"
        processor.check.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Write Pipeline implementation**

Create `src/boozarr/pipeline.py`:

```python
"""Pipeline orchestrator — runs processors in sequence per EPUB file."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from boozarr.epub import EpubWrapper


class Pipeline:
    def __init__(
        self, db: Any, processors: list[Any],
        config: dict[str, Any], fix: bool = False,
    ) -> None:
        self.db = db
        self.processors = processors
        self.config = config
        self.fix = fix

    def process_epub(self, epub_path: Path) -> dict[str, Any]:
        try:
            wrapper = EpubWrapper(epub_path)
        except (FileNotFoundError, ValueError) as exc:
            return {"file_path": str(epub_path), "status": "error",
                    "issues": 0, "fixes": 0, "error": str(exc)}

        existing = self.db.lookup_hash(wrapper.file_hash)
        if existing == "ok":
            return {"file_path": str(epub_path), "status": "skip",
                    "issues": 0, "fixes": 0}

        total_issues = 0
        total_fixes = 0
        overall_status = "ok"

        for processor in self.processors:
            try:
                issues = processor.check(wrapper)
                total_issues += len(issues)
                self.db.log_event(str(epub_path), processor.name, "check", f"{len(issues)} issues")
                if self.fix and issues:
                    fixes = processor.fix(wrapper, issues, self.config)
                    total_fixes += len(fixes)
                    self.db.log_event(str(epub_path), processor.name, "fix", f"{len(fixes)} fixes")
            except Exception:
                self.db.log_event(str(epub_path), processor.name, "error", traceback.format_exc())
                overall_status = "error"

        db_status = "ok" if overall_status == "ok" and total_issues == 0 else "warn"
        self.db.record_file(str(epub_path), wrapper.file_hash, db_status,
                            total_issues, total_fixes, dry_run=not self.fix)
        return {"file_path": str(epub_path), "status": db_status,
                "issues": total_issues, "fixes": total_fixes}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/pipeline.py tests/test_pipeline.py
git commit -m "feat: add Pipeline orchestrator"
```

---

### Task 5: Chapters processor

**Files:**
- Create: `src/boozarr/processors/chapters.py`
- Test: `tests/test_processors/test_chapters.py`

- [ ] **Step 1: Write failing tests**

```bash
mkdir -p tests/test_processors
touch tests/test_processors/__init__.py
```

Create `tests/test_processors/test_chapters.py`:

```python
"""Tests for Chapters processor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.chapters import ChaptersProcessor


class TestChaptersCheck:
    def test_no_issues_when_toc_exists(self) -> None:
        epub = MagicMock()
        epub.read_ncx.return_value = [{"label": "Ch1", "src": "ch1.xhtml"}]
        processor = ChaptersProcessor()
        issues = processor.check(epub)
        assert len(issues) == 0

    def test_issue_when_toc_empty(self) -> None:
        epub = MagicMock()
        epub.read_ncx.return_value = []
        processor = ChaptersProcessor()
        issues = processor.check(epub)
        assert len(issues) == 1
        assert issues[0].processor == "chapters"
        assert issues[0].fix_possible is True

    def test_detects_heading_in_xhtml(self) -> None:
        epub = MagicMock()
        epub.read_ncx.return_value = []
        epub.xhtml_files = [
            {"path": "OEBPS/ch1.xhtml", "content": "<html><body><h1>Chapter 1</h1><p>text</p></body></html>"},
            {"path": "OEBPS/ch2.xhtml", "content": "<html><body><h1>Chapter 2</h1><p>text</p></body></html>"},
        ]
        processor = ChaptersProcessor()
        issues = processor.check(epub)
        assert len(issues) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_processors/test_chapters.py -v`
Expected: FAIL

- [ ] **Step 3: Write ChaptersProcessor**

Create `src/boozarr/processors/chapters.py`:

```python
"""Chapter detection and ToC injection processor."""

from __future__ import annotations

import re
from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_CHAPTER_PATTERNS = [
    re.compile(r"^Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"^Part\s+\d+", re.IGNORECASE),
    re.compile(r"^Section\s+\d+", re.IGNORECASE),
    re.compile(r"^CHAPTER\s+\w+"),
]


class ChaptersProcessor(BaseProcessor):
    name = "chapters"

    def check(self, epub: Any) -> list[Issue]:
        try:
            ncx_entries = epub.read_ncx()
        except Exception:
            ncx_entries = []
        if ncx_entries and len(ncx_entries) > 0:
            return []
        return [Issue(
            processor=self.name, severity="warn",
            location="toc.ncx / nav.xhtml",
            description="No chapter entries found in table of contents",
            fix_possible=True,
        )]

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        fixes: list[Fix] = []
        discovered: list[tuple[str, str]] = []
        for xhtml_file in getattr(epub, "xhtml_files", []):
            content = xhtml_file.get("content", "")
            path = xhtml_file.get("path", "")
            for pattern in _CHAPTER_PATTERNS:
                match = pattern.search(content)
                if match:
                    discovered.append((path, match.group(0)))
                    break
        if discovered:
            fixes.append(Fix(
                processor=self.name, location="toc.ncx",
                description=f"Added {len(discovered)} chapter entries from content scan",
                old_value="",
                new_value=f"<navMap>{' '.join(c[1] for c in discovered)}</navMap>",
            ))
        return fixes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_processors/test_chapters.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/processors/chapters.py tests/test_processors/
git commit -m "feat: add Chapters processor"
```

---

### Task 6: Borders & Margins processor

**Files:**
- Create: `src/boozarr/processors/borders.py`
- Test: `tests/test_processors/test_borders.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_processors/test_borders.py`:

```python
"""Tests for Borders processor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.borders import BordersProcessor


class TestBordersCheck:
    def test_no_issues_when_all_match(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"border": "none", "margin": "1em", "padding": "0"}
        processor = BordersProcessor()
        issues = processor.check(epub)
        assert len(issues) == 0

    def test_issue_when_border_mismatch(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"border": "2px solid red", "margin": "1em", "padding": "0"}
        processor = BordersProcessor()
        issues = processor.check(epub)
        assert len(issues) >= 1
        assert any("border" in i.location for i in issues)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_processors/test_borders.py -v`
Expected: FAIL

- [ ] **Step 3: Write BordersProcessor**

Create `src/boozarr/processors/borders.py`:

```python
"""CSS border/margin/padding normalisation processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_TARGET_PROPS = ["border", "border-width", "margin", "padding",
                 "margin-left", "margin-right", "padding-left", "padding-right"]


class BordersProcessor(BaseProcessor):
    name = "borders"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        props = getattr(epub, "css_properties", {})
        for prop in _TARGET_PROPS:
            value = props.get(prop)
            if value and value not in ("none", "0", "1em"):
                issues.append(Issue(
                    processor=self.name, severity="info",
                    location=f"CSS ({prop})",
                    description=f"Non-standard {prop}: '{value}'",
                    fix_possible=True,
                ))
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        return [Fix(
            processor=self.name, location=i.location,
            description=f"Normalised {i.location}",
            old_value=i.description, new_value="target value applied",
        ) for i in issues]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_processors/test_borders.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/processors/borders.py tests/test_processors/test_borders.py
git commit -m "feat: add Borders processor"
```

---

### Task 7: Remaining processors (Metadata, CSS Normalise, Links, Compression)

**Files:**
- Create: `src/boozarr/processors/metadata.py`
- Create: `src/boozarr/processors/css_normalise.py`
- Create: `src/boozarr/processors/links.py`
- Create: `src/boozarr/processors/compression.py`
- Test: `tests/test_processors/test_metadata.py`
- Test: `tests/test_processors/test_css_normalise.py`
- Test: `tests/test_processors/test_links.py`
- Test: `tests/test_processors/test_compression.py`

Each processor follows the same pattern as Tasks 5–6:

- [ ] **Step 1: Metadata processor** (`processors/metadata.py`)
  - `check()`: Read OPF `<metadata>`, report missing `dc:title`, `dc:creator`, `dc:publisher`, `dc:date`, `dc:language`.
  - `fix()`: Infer from filename (`Author - Title.epub`), default language to `en`.
  - Test: create valid+empty+missing OPF metadata scenarios.

- [ ] **Step 2: CSS Normalise processor** (`processors/css_normalise.py`)
  - `check()`: Scan CSS for font-size, line-height, text-align on `p`, `div`, `section`, `body`.
  - `fix()`: Replace with configured targets (`font_size`, `line_height`, `paragraph_spacing` from config).
  - Test: mock `epub.css_properties` with mismatched values.

- [ ] **Step 3: Links processor** (`processors/links.py`)
  - `check()`: Parse internal `href` attributes, verify targets exist. Optionally HEAD-check external URLs when `check_external_links=True` in config.
  - `fix()`: Report-only for external; optionally comment out broken internal refs.
  - Test: mock `epub.internal_links` and `epub.external_links`.

- [ ] **Step 4: Compression processor** (`processors/compression.py`)
  - `check()`: Report file count, compression ratio, presence of `.DS_Store`, `thumbs.db`, empty dirs.
  - `fix()`: Strip extraneous files, re-zip with optimal compression.
  - Test: mock `epub.extra_files` list.

- [ ] **Step 5: Run all processor tests**

Run: `uv run pytest tests/test_processors/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/boozarr/processors/ tests/test_processors/
git commit -m "feat: add Metadata, CSS Normalise, Links, Compression processors"
```

---

### Task 8: Wire everything together — update CLI entry point

**Files:**
- Modify: `src/boozarr/cli.py`
- Test: `tests/test_cli.py` (new)

- [ ] **Step 1: Write failing CLI integration tests**

Create `tests/test_cli.py`:

```python
"""Tests for the boozarr CLI entry point."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from boozarr.cli import cli


class TestCliBase:
    def test_help_succeeds(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "boozarr" in result.output

    def test_version_succeeds(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0

    def test_requires_library_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code != 0
        assert "--library-path" in result.output

    def test_dry_run_no_modifications(self, tmp_path: Path) -> None:
        runner = CliRunner()
        lib_dir = tmp_path / "library"
        lib_dir.mkdir()
        epub_path = lib_dir / "book.epub"
        epub_path.write_text("dummy epub content")
        result = runner.invoke(cli, ["--library-path", str(lib_dir)])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — CLI not yet wired with all options

- [ ] **Step 3: Rewrite `src/boozarr/cli.py`**

Replace the skeleton with the full Click entry point:

```python
"""Command-line interface for boozarr."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click

from boozarr.db import ProcessingDB
from boozarr.logger import create_logger
from boozarr.pipeline import Pipeline
from boozarr.processors.borders import BordersProcessor
from boozarr.processors.chapters import ChaptersProcessor
from boozarr.processors.compression import CompressionProcessor
from boozarr.processors.css_normalise import CssNormaliseProcessor
from boozarr.processors.links import LinksProcessor
from boozarr.processors.metadata import MetadataProcessor
from boozarr.report import Report
from boozarr.utils import get_project_root

try:
    _VERSION = version("boozarr")
except PackageNotFoundError:
    _VERSION = "unknown"

_PROJECT_ROOT = get_project_root()
_DEFAULT_DB_PATH = f"{_PROJECT_ROOT}/db/boozarr.db"
_DEFAULT_LOGS_PATH = f"{_PROJECT_ROOT}/logs/boozarr.log"


@click.command(context_settings={"show_default": True})
@click.option("--library-path", required=True, type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True), metavar="<DIR>", help="Directory containing EPUB files.")
@click.option("--fix", is_flag=True, default=False, help="Apply fixes (default: dry-run).")
@click.option("--backup", is_flag=True, default=False, help="Create .bak copies before modifying.")
@click.option("--db-path", default=_DEFAULT_DB_PATH, type=click.Path(file_okay=True, dir_okay=False, resolve_path=True), metavar="<path>", help="SQLite DB path.")
@click.option("--log-path", default=_DEFAULT_LOGS_PATH, type=click.Path(file_okay=True, dir_okay=False, resolve_path=True), metavar="<path>", help="Log file path.")
@click.option("--log-level", type=click.Choice(["DEBUG","INFO","SUCCESS","WARNING","ERROR"], case_sensitive=False), default="INFO", metavar="<level>", help="Logging level.")
@click.option("--skip-chapters", is_flag=True, help="Skip chapter detection.")
@click.option("--skip-borders", is_flag=True, help="Skip border normalisation.")
@click.option("--skip-metadata", is_flag=True, help="Skip metadata fixer.")
@click.option("--skip-css", is_flag=True, help="Skip CSS normalisation.")
@click.option("--skip-links", is_flag=True, help="Skip link checker.")
@click.option("--no-compress", is_flag=True, help="Skip compression.")
@click.option("--border", default="none", metavar="<val>", help="Target border.")
@click.option("--margin", default="1em", metavar="<val>", help="Target margin.")
@click.option("--padding", default="0", metavar="<val>", help="Target padding.")
@click.option("--font-size", default="1em", metavar="<val>", help="Target font size.")
@click.option("--line-height", default="1.5", metavar="<val>", help="Target line height.")
@click.option("--paragraph-spacing", default="1em", metavar="<val>", help="Target paragraph spacing.")
@click.option("--check-external-links", is_flag=True, help="Validate external URLs.")
@click.version_option(version=_VERSION, prog_name="boozarr")
def cli(
    library_path: str, fix: bool, backup: bool, db_path: str,
    log_path: str, log_level: str,
    skip_chapters: bool, skip_borders: bool, skip_metadata: bool,
    skip_css: bool, skip_links: bool, no_compress: bool,
    border: str, margin: str, padding: str, font_size: str,
    line_height: str, paragraph_spacing: str,
    check_external_links: bool,
) -> None:
    """Boozarr - Automated EPUB Editor.

    Batch-process EPUB files: run checks and fixes for chapters, borders,
    metadata, CSS, links, and compression across an entire library.
    """
    logger = create_logger(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        log_level, log_path,
    )

    db = ProcessingDB(Path(db_path))

    processors = []
    if not skip_chapters:
        processors.append(ChaptersProcessor())
    if not skip_borders:
        processors.append(BordersProcessor())
    if not skip_metadata:
        processors.append(MetadataProcessor())
    if not skip_css:
        processors.append(CssNormaliseProcessor())
    if not skip_links:
        processors.append(LinksProcessor())
    if not no_compress:
        processors.append(CompressionProcessor())

    config = {
        "border": border, "margin": margin, "padding": padding,
        "font_size": font_size, "line_height": line_height,
        "paragraph_spacing": paragraph_spacing,
        "check_external_links": check_external_links,
    }

    pipeline = Pipeline(db=db, processors=processors, config=config, fix=fix)
    report = Report()

    lib_path = Path(library_path)
    epub_files = sorted(lib_path.rglob("*.epub"))

    if not epub_files:
        logger.warning("No .epub files found in {}", library_path)
        return

    logger.info("Found {} EPUB files in {}", len(epub_files), library_path)

    for epub_file in epub_files:
        result = pipeline.process_epub(epub_file)
        line = report.log_line(
            result["file_path"], result["status"],
            issues=result["issues"], fixes=result["fixes"],
        )
        logger.info(line)

    summary = report.final_summary(duration_s=0.0)
    logger.info("Summary:\n{}", summary)
    db.close()


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Add missing dependencies to pyproject.toml**

Add `"ebooklib"`, `"lxml"`, `"tinycss2"` to the `dependencies` list in `pyproject.toml`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/boozarr/cli.py tests/test_cli.py pyproject.toml
git commit -m "feat: wire CLI entry point with all processors"
```

---

### Task 9: Full integration and QA

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -v
```
Expected: ALL tests pass (rename tests + unit tests for every module)

- [ ] **Step 2: Run linter and type checker**

```bash
uv run ruff check src/boozarr/ tests/
uv run ruff format --check src/boozarr/ tests/
uv run mypy src/boozarr/
```
Expected: All clean

- [ ] **Step 3: Run pre-commit**

```bash
uv run pre-commit run --all-files
```
Expected: All hooks pass

- [ ] **Step 4: Final commit if any QA fixes were needed**

```bash
git add -A
git commit -m "chore: fix lint/type issues from QA"
```
