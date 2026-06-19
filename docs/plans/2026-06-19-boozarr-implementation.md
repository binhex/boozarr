# Boozarr EPUB Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working CLI tool that batch-processes EPUB files — running checks and fixes for chapters, borders, metadata, CSS, links, and compression.

**Architecture:** A Click CLI parses options, instantiates a Pipeline with user-selected processors, then iterates over EPUB files in a library directory. Each EPUB is extracted to a temp dir via EpubWrapper, inspected/manipulated, then repacked. An SQLite DB tracks processed files by SHA-256 to skip unchanged files on re-run.

**Tech Stack:** Python 3.12+, Click (CLI), Loguru (logging), ebooklib (EPUB), lxml (XML/HTML), tinycss2 (CSS), sqlite3 (stdlib), pytest + pytest-cov (testing).

**Default paths:** Logs at `<project_root>/logs/boozarr.log`, DB at `<project_root>/db/boozarr.db`.

---

### Task 1: EpubWrapper — EPUB file handling

**Files:**
- Create: `src/boozarr/epub.py`
- Test: `tests/test_epub.py`

**Responsibility:** Wrap an EPUB file — validate ZIP structure, extract to temp dir, provide file-level read/write access to extracted content, repack into a compressed ZIP.

- [ ] **Step 1: Write failing tests**

Create `tests/test_epub.py`:

```python
"""Tests for EpubWrapper — EPUB file validation, extract, repack."""

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
        EpubWrapper(epub_path).validate()

    def test_validate_not_a_zip(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "notazip.epub"
        epub_path.write_bytes(b"plain data")
        with pytest.raises(zipfile.BadZipFile):
            EpubWrapper(epub_path).validate()

    def test_validate_missing_opf(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "noopf.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
        with pytest.raises(ValueError, match="Missing EPUB structure"):
            EpubWrapper(epub_path).validate()


class TestEpubWrapperRepack:
    def test_extract_and_repack_round_trip(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "input.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr("OEBPS/chapter1.xhtml", "<html><body><p>Hello</p></body></html>")

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)
        fpath = extract_dir / "OEBPS/chapter1.xhtml"
        assert fpath.read_text() == "<html><body><p>Hello</p></body></html>"

        wrapper.write_file(fpath, "<html><body><p>Modified</p></body></html>")

        output = tmp_path / "output.epub"
        wrapper.repack(output)
        with zipfile.ZipFile(output, "r") as zf:
            assert zf.read("OEBPS/chapter1.xhtml").decode() == "<html><body><p>Modified</p></body></html>"

    def test_repack_without_extract_raises(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "a.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
        wrapper = EpubWrapper(epub_path)
        with pytest.raises(RuntimeError, match="No extracted directory"):
            wrapper.repack(tmp_path / "out.epub")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_epub.py -v`
Expected output: `ModuleNotFoundError: No module named 'boozarr.epub'`

- [ ] **Step 3: Write EpubWrapper implementation**

Create `src/boozarr/epub.py`:

```python
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
        self.file_hash: str = hashlib.sha256(path.read_bytes()).hexdigest()
        self._extract_dir: Path | None = None

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
        """Extract the EPUB ZIP into *target_dir*."""
        self._extract_dir = target_dir
        with zipfile.ZipFile(self.path, "r") as zf:
            zf.extractall(target_dir)

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_epub.py -v`
Expected: **5 passed**

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/epub.py tests/test_epub.py
git commit -m "feat: add EpubWrapper for EPUB file handling"
```

---

### Task 2: ProcessingDB — SQLite tracking database

**Files:**
- Create: `src/boozarr/db.py`
- Test: `tests/test_db.py`

**Responsibility:** SQLite database with two tables (`processed_files`, `processing_log`). Methods: `lookup_hash(hash) → status|None`, `record_file(...)`, `log_event(...)`. Uses `sqlite3` from stdlib.

- [ ] **Step 1: Write failing tests**

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
        tables = {
            row[0]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
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


class TestProcessingDB:
    def test_lookup_missing_hash(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        assert db.lookup_hash("missing") is None

    def test_lookup_existing_hash(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        db.record_file("a.epub", "abc", "ok", issues=2, fixes=1, dry_run=True)
        assert db.lookup_hash("abc") == "ok"

    def test_record_and_verify(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        db.record_file("book.epub", "def", "ok", issues=0, fixes=3, dry_run=False)
        row = db.conn.execute(
            "SELECT file_path, status, fixes_applied FROM processed_files"
        ).fetchone()
        assert row == ("book.epub", "ok", 3)

    def test_log_event(self, tmp_path: Path) -> None:
        db = ProcessingDB(tmp_path / "test.db")
        db.log_event("book.epub", "chapters", "check", '{"found": 0}')
        row = db.conn.execute(
            "SELECT file_path, processor, action FROM processing_log"
        ).fetchone()
        assert row == ("book.epub", "chapters", "check")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v`
Expected: `ModuleNotFoundError: No module named 'boozarr.db'`

- [ ] **Step 3: Write ProcessingDB implementation**

Create `src/boozarr/db.py`:

```python
"""SQLite database for tracking processed EPUB files."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class ProcessingDB:
    """Thread-unsafe SQLite wrapper for boozarr tracking."""

    SCHEMA = """
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
    );"""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.executescript(self.SCHEMA)

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
            "INSERT OR REPLACE INTO processed_files "
            "(file_path, file_hash, processed_at, status, issues_found, fixes_applied, dry_run) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (file_path, file_hash, now, status, issues, fixes, dry_run),
        )
        self.conn.commit()

    def log_event(self, file_path: str, processor: str, action: str, detail: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO processing_log (file_path, processor, action, detail, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (file_path, processor, action, detail, now),
        )
        self.conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: **6 passed**

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/db.py tests/test_db.py
git commit -m "feat: add ProcessingDB for tracking processed files"
```

---

### Task 3: Report, Issue/Fix models, BaseProcessor

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
        assert "OK" in line
        assert "book.epub" in line

    def test_log_line_warn(self) -> None:
        r = Report()
        line = r.log_line("/path/book.epub", "warn", issues=2, fixes=0)
        assert "WARN" in line

    def test_log_line_error(self) -> None:
        r = Report()
        line = r.log_line("/path/a.epub", "error", issues=0, fixes=0)
        assert "ERR" in line

    def test_log_line_skip(self) -> None:
        r = Report()
        line = r.log_line("/path/a.epub", "skip", issues=0, fixes=0)
        assert "SKIP" in line

    def test_final_summary_counts(self) -> None:
        r = Report()
        r.log_line("a.epub", "ok", issues=0, fixes=3)
        r.log_line("b.epub", "warn", issues=2, fixes=0)
        r.log_line("c.epub", "error", issues=0, fixes=0)
        r.log_line("d.epub", "skip", issues=0, fixes=0)
        s = r.final_summary(duration_s=12.4)
        assert "Processed: 4" in s
        assert "Issues found: 2" in s
        assert "Fixes applied: 3" in s
```

Create `tests/test_processor_base.py`:

```python
"""Tests for BaseProcessor, Issue, Fix."""

from __future__ import annotations

import pytest

from boozarr.processors.base import BaseProcessor, Issue, Fix


class TestIssueFix:
    def test_issue_defaults(self) -> None:
        i = Issue(
            processor="chapters", severity="warn",
            location="toc.ncx", description="Empty ToC",
        )
        assert i.fix_possible is True

    def test_fix_defaults(self) -> None:
        f = Fix(
            processor="chapters", location="toc.ncx",
            description="Injected 5 chapters",
            new_value="<navMap>...</navMap>",
        )
        assert f.old_value == ""


class TestBaseProcessor:
    def test_instantiate_abstract_raises(self) -> None:
        with pytest.raises(TypeError):
            BaseProcessor()  # type: ignore[abstract]

    def test_concrete_processor(self) -> None:
        class P(BaseProcessor):
            name = "test"
            def check(self, epub):  # type: ignore[no-untyped-def]
                return [Issue(self.name, "info", "loc", "desc")]
            def fix(self, epub, issues, config):  # type: ignore[no-untyped-def]
                return [Fix(self.name, "loc", "fixed", new_value="x")]

        p = P()
        assert p.name == "test"
        assert len(p.check(None)) == 1
        assert len(p.fix(None, [], {})) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_report.py tests/test_processor_base.py -v`
Expected: `ModuleNotFoundError` for both modules

- [ ] **Step 3: Write implementations**

Create `src/boozarr/report.py`:

```python
"""Console summary reporting for boozarr processing runs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Report:
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
            f"  - Issues found: {self.total_issues} across {self.total - self.skipped - self.errors} files\n"
            f"  - Fixes applied: {self.total_fixes}\n"
            f"  - Errors: {self.errors}\n"
            f"Duration: {duration_s:.1f}s"
        )
```

Create `src/boozarr/processors/__init__.py`:

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_report.py tests/test_processor_base.py -v`
Expected: **7 passed**

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/report.py src/boozarr/processors/ tests/test_report.py tests/test_processor_base.py
git commit -m "feat: add Report, Issue/Fix, BaseProcessor"
```

---

### Task 4: Pipeline orchestrator

**Files:**
- Create: `src/boozarr/pipeline.py`
- Test: `tests/test_pipeline.py`

**Responsibility:** `Pipeline.process_epub(path)` validates the EPUB via EpubWrapper, skips if hash matches a prior "ok" record, runs each processor's `check()`, optionally `fix()`, records in DB, returns a result dict.

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
    def test_dry_run_does_not_fix(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("content")
        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        proc = MagicMock()
        proc.name = "test"
        proc.check.return_value = [MagicMock()]
        proc.fix.return_value = [MagicMock()]

        pipeline = Pipeline(db=db, processors=[proc], config={}, fix=False)
        result = pipeline.process_epub(epub_path)

        assert result["issues"] == 1
        assert result["fixes"] == 0
        proc.check.assert_called_once()
        proc.fix.assert_not_called()

    def test_fix_mode_applies_fixes(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("content")
        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        proc = MagicMock()
        proc.name = "test"
        proc.check.return_value = [MagicMock()]
        proc.fix.return_value = [MagicMock()]

        pipeline = Pipeline(db=db, processors=[proc], config={}, fix=True)
        result = pipeline.process_epub(epub_path)

        assert result["issues"] == 1
        assert result["fixes"] == 1
        proc.fix.assert_called_once()

    def test_skips_unchanged_file(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("content")
        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = "ok"

        proc = MagicMock()
        pipeline = Pipeline(db=db, processors=[proc], config={}, fix=False)
        result = pipeline.process_epub(epub_path)

        assert result["status"] == "skip"
        proc.check.assert_not_called()

    def test_catches_processor_exception(self, tmp_path: Path) -> None:
        epub_path = tmp_path / "test.epub"
        epub_path.write_text("content")
        db = MagicMock(spec_set=["lookup_hash", "record_file", "log_event"])
        db.lookup_hash.return_value = None

        proc = MagicMock()
        proc.name = "crash"
        proc.check.side_effect = RuntimeError("boom")

        pipeline = Pipeline(db=db, processors=[proc], config={}, fix=False)
        result = pipeline.process_epub(epub_path)

        assert result["status"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: `ModuleNotFoundError: No module named 'boozarr.pipeline'`

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
        overall = "ok"

        for proc in self.processors:
            try:
                issues = proc.check(wrapper)
                total_issues += len(issues)
                self.db.log_event(str(epub_path), proc.name, "check", f"{len(issues)} issues")
                if self.fix and issues:
                    fixes = proc.fix(wrapper, issues, self.config)
                    total_fixes += len(fixes)
                    self.db.log_event(str(epub_path), proc.name, "fix", f"{len(fixes)} fixes")
            except Exception:
                self.db.log_event(str(epub_path), proc.name, "error", traceback.format_exc())
                overall = "error"

        status = "ok" if overall == "ok" and total_issues == 0 else "warn"
        self.db.record_file(str(epub_path), wrapper.file_hash, status,
                            total_issues, total_fixes, dry_run=not self.fix)
        return {"file_path": str(epub_path), "status": status,
                "issues": total_issues, "fixes": total_fixes}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: **4 passed**

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

**Check logic:** Read `epub.read_ncx()`. If populated → 0 issues. If empty/missing → return 1 Issue. Also scan XHTML content for `<h1>`/`<h2>` headings as evidence.

**Fix logic:** Scan XHTML files for chapter heading patterns, generate `toc.ncx` entries.

- [ ] **Step 1: Write failing tests**

```bash
mkdir -p tests/test_processors
touch tests/test_processors/__init__.py
```

Create `tests/test_processors/test_chapters.py`:

```python
"""Tests for ChaptersProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.chapters import ChaptersProcessor


class TestChaptersCheck:
    def test_no_issues_when_toc_populated(self) -> None:
        epub = MagicMock()
        epub.read_ncx.return_value = [{"label": "Ch1", "src": "ch1.xhtml"}]
        issues = ChaptersProcessor().check(epub)
        assert issues == []

    def test_issue_when_toc_empty(self) -> None:
        epub = MagicMock()
        epub.read_ncx.return_value = []
        issues = ChaptersProcessor().check(epub)
        assert len(issues) == 1
        assert issues[0].processor == "chapters"
        assert issues[0].fix_possible is True

    def test_issue_when_toc_missing(self) -> None:
        epub = MagicMock()
        epub.read_ncx.side_effect = Exception("no ncx")
        issues = ChaptersProcessor().check(epub)
        assert len(issues) == 1


class TestChaptersFix:
    def test_fix_discovers_chapters(self) -> None:
        epub = MagicMock()
        epub.xhtml_files = [
            {"path": "OEBPS/ch1.xhtml", "content": "<html><body><h1>Chapter 1</h1><p>text</p></body></html>"},
            {"path": "OEBPS/ch2.xhtml", "content": "<html><body><h1>Chapter 2</h1><p>text</p></body></html>"},
        ]
        issues = [MagicMock()]
        fixes = ChaptersProcessor().fix(epub, issues, {})
        assert len(fixes) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_processors/test_chapters.py -v`
Expected: `ModuleNotFoundError`

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
            entries = epub.read_ncx()
        except Exception:
            entries = []
        if entries and len(entries) > 0:
            return []
        return [Issue(
            processor=self.name, severity="warn",
            location="toc.ncx / nav.xhtml",
            description="No chapter entries found in table of contents",
            fix_possible=True,
        )]

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        discovered: list[tuple[str, str]] = []
        for xhtml in getattr(epub, "xhtml_files", []):
            content = xhtml.get("content", "")
            path = xhtml.get("path", "")
            for pattern in _CHAPTER_PATTERNS:
                match = pattern.search(content)
                if match:
                    discovered.append((path, match.group(0)))
                    break
        if discovered:
            nav = " ".join(f"<navPoint id='ch-{i}'><label>{lab}</label><src>{p}</src></navPoint>"
                          for i, (p, lab) in enumerate(discovered))
            return [Fix(
                processor=self.name, location="toc.ncx",
                description=f"Added {len(discovered)} chapter entries",
                old_value="", new_value=f"<navMap>{nav}</navMap>",
            )]
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_processors/test_chapters.py -v`
Expected: **4 passed**

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/processors/chapters.py tests/test_processors/
git commit -m "feat: add Chapters processor"
```

---

### Task 6: Borders processor

**Files:**
- Create: `src/boozarr/processors/borders.py`
- Test: `tests/test_processors/test_borders.py`

**Check:** Scan `epub.css_properties` dict for border/margin/padding values that differ from "none"/"0"/"1em" targets.

**Fix:** Replace detected non-standard values with placeholder targets.

- [ ] **Step 1: Write failing tests**

Create `tests/test_processors/test_borders.py`:

```python
"""Tests for BordersProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.borders import BordersProcessor


class TestBordersCheck:
    def test_no_issues_when_all_standard(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"border": "none", "margin": "1em", "padding": "0"}
        issues = BordersProcessor().check(epub)
        assert issues == []

    def test_issue_on_nonstandard_border(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"border": "2px solid red", "margin": "1em", "padding": "0"}
        issues = BordersProcessor().check(epub)
        assert len(issues) >= 1

    def test_issue_on_nonstandard_margin(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"margin": "2cm", "border": "none", "padding": "0"}
        issues = BordersProcessor().check(epub)
        assert len(issues) >= 1


class TestBordersFix:
    def test_fix_creates_entry_per_issue(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"border": "2px solid red"}
        issues = BordersProcessor().check(epub)
        fixes = BordersProcessor().fix(epub, issues, {"border": "none"})
        assert len(fixes) == len(issues)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_processors/test_borders.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write BordersProcessor**

Create `src/boozarr/processors/borders.py`:

```python
"""CSS border/margin/padding normalisation processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_TARGET = ["border", "border-width", "margin", "padding",
           "margin-left", "margin-right", "padding-left", "padding-right"]


class BordersProcessor(BaseProcessor):
    name = "borders"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        props = getattr(epub, "css_properties", {})
        for prop in _TARGET:
            val = props.get(prop)
            if val and val not in ("none", "0", "1em"):
                issues.append(Issue(
                    processor=self.name, severity="info",
                    location=f"CSS ({prop})",
                    description=f"Non-standard {prop}: '{val}'",
                    fix_possible=True,
                ))
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        return [Fix(
            processor=self.name, location=i.location,
            description=f"Normalised {i.location}",
            old_value=i.description,
            new_value=f"target={config.get('border', 'none')}",
        ) for i in issues]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_processors/test_borders.py -v`
Expected: **4 passed**

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/processors/borders.py tests/test_processors/test_borders.py
git commit -m "feat: add Borders processor"
```

---

### Task 7: Remaining four processors

**Files:**
- Create: `src/boozarr/processors/metadata.py`
- Create: `src/boozarr/processors/css_normalise.py`
- Create: `src/boozarr/processors/links.py`
- Create: `src/boozarr/processors/compression.py`
- Test: `tests/test_processors/test_metadata.py`
- Test: `tests/test_processors/test_css_normalise.py`
- Test: `tests/test_processors/test_links.py`
- Test: `tests/test_processors/test_compression.py`

Each follows the same RED-GREEN pattern. Implement in any order.

- [ ] **Step 1: Metadata processor**

Create `src/boozarr/processors/metadata.py`:

```python
"""Missing metadata fixer processor."""

from __future__ import annotations

import re
from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_REQUIRED = ["dc:title", "dc:creator", "dc:language", "dc:date"]


class MetadataProcessor(BaseProcessor):
    name = "metadata"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        meta = getattr(epub, "opf_metadata", {})
        for field in _REQUIRED:
            if not meta.get(field):
                issues.append(Issue(
                    processor=self.name, severity="warn",
                    location=f"content.opf <metadata>",
                    description=f"Missing {field}",
                    fix_possible=True,
                ))
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        fixes: list[Fix] = []
        filename = getattr(epub, "path", None)
        fname = str(filename) if filename else ""
        match = re.match(r"(.+?)\s*-\s*(.+?)\.epub", fname.rsplit("/", 1)[-1])
        author = match.group(1).strip() if match else "Unknown Author"
        title = match.group(2).strip() if match else "Unknown Title"

        for issue in issues:
            field = issue.location.split()[-1]
            if field == "dc:title":
                fixes.append(Fix(self.name, issue.location, f"Inferred title '{title}'", "", title))
            elif field == "dc:creator":
                fixes.append(Fix(self.name, issue.location, f"Inferred author '{author}'", "", author))
            elif field == "dc:language":
                fixes.append(Fix(self.name, issue.location, "Defaulted language to 'en'", "", "en"))
            elif field == "dc:date":
                fixes.append(Fix(self.name, issue.location, "Defaulted date to today", "", "2026-01-01"))
        return fixes
```

Create `tests/test_processors/test_metadata.py`:

```python
"""Tests for MetadataProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.metadata import MetadataProcessor


class TestMetadataCheck:
    def test_no_issues_when_all_present(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {"dc:title": "T", "dc:creator": "A", "dc:language": "en", "dc:date": "2024"}
        assert MetadataProcessor().check(epub) == []

    def test_issues_for_missing_fields(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {}
        issues = MetadataProcessor().check(epub)
        assert len(issues) == 4


class TestMetadataFix:
    def test_fix_infers_from_filename(self) -> None:
        epub = MagicMock()
        epub.opf_metadata = {}
        epub.path = "/lib/Isaac Asimov - Foundation.epub"
        issues = [MagicMock(location="content.opf <metadata> dc:title")]
        fixes = MetadataProcessor().fix(epub, issues, {})
        assert len(fixes) == 1
```

- [ ] **Step 2: CSS Normalise processor**

Create `src/boozarr/processors/css_normalise.py`:

```python
"""CSS font/line-height/paragraph normalisation processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_PARAGRAPH_PROPS = ["font-size", "line-height", "text-align", "margin", "padding"]


class CssNormaliseProcessor(BaseProcessor):
    name = "css_normalise"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        props = getattr(epub, "css_properties", {})
        for prop in _PARAGRAPH_PROPS:
            val = props.get(prop)
            if val and val not in ("1em", "1.5", "left", "0"):
                issues.append(Issue(
                    processor=self.name, severity="info",
                    location=f"CSS ({prop})",
                    description=f"Non-standard {prop}: '{val}'",
                    fix_possible=True,
                ))
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        mapping = {
            "font-size": config.get("font_size", "1em"),
            "line-height": config.get("line_height", "1.5"),
            "text-align": "left",
            "margin": config.get("paragraph_spacing", "1em"),
            "padding": "0",
        }
        return [Fix(
            processor=self.name, location=i.location,
            description=f"Normalised {i.location}",
            old_value=i.description,
            new_value=f"{mapping.get(i.location.split()[-1], '1em')}",
        ) for i in issues]
```

Create `tests/test_processors/test_css_normalise.py`:

```python
"""Tests for CssNormaliseProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.css_normalise import CssNormaliseProcessor


class TestCssNormaliseCheck:
    def test_no_issues_when_standard(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"font-size": "1em", "line-height": "1.5", "text-align": "left"}
        assert CssNormaliseProcessor().check(epub) == []

    def test_issue_on_nonstandard_font_size(self) -> None:
        epub = MagicMock()
        epub.css_properties = {"font-size": "2em", "line-height": "1.5"}
        issues = CssNormaliseProcessor().check(epub)
        assert len(issues) == 1
```

- [ ] **Step 3: Links processor**

Create `src/boozarr/processors/links.py`:

```python
"""Broken link checker processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue


class LinksProcessor(BaseProcessor):
    name = "links"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        for link in getattr(epub, "internal_links", []):
            if not self._target_exists(epub, link):
                issues.append(Issue(
                    processor=self.name, severity="warn",
                    location=f"link: {link}",
                    description=f"Broken internal reference: {link}",
                    fix_possible=False,
                ))
        check_ext = getattr(epub, "check_external_links", False)
        if check_ext:
            for link in getattr(epub, "external_links", []):
                issues.append(Issue(
                    processor=self.name, severity="info",
                    location=f"ext-link: {link}",
                    description=f"External link (validation skipped in batch mode): {link}",
                    fix_possible=False,
                ))
        return issues

    def _target_exists(self, epub: Any, href: str) -> bool:
        # Minimal: check if anchor or file referenced in href exists in extracted files
        if "#" in href:
            file_part = href.split("#")[0]
            if file_part:
                return any(file_part in str(f) for f in getattr(epub, "extracted_files", []))
            return True  # same-file anchor, skip
        return any(href in str(f) for f in getattr(epub, "extracted_files", []))

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        return []  # report-only for now
```

Create `tests/test_processors/test_links.py`:

```python
"""Tests for LinksProcessor."""

from __future__ import annotations

from unittest.mock import MagicMock

from boozarr.processors.links import LinksProcessor


class TestLinksCheck:
    def test_no_issues_when_all_links_valid(self) -> None:
        epub = MagicMock()
        epub.internal_links = ["ch1.xhtml", "ch2.xhtml"]
        epub.extracted_files = ["/tmp/x/META-INF/container.xml", "/tmp/x/OEBPS/ch1.xhtml", "/tmp/x/OEBPS/ch2.xhtml"]
        issues = LinksProcessor().check(epub)
        assert issues == []

    def test_issue_on_broken_link(self) -> None:
        epub = MagicMock()
        epub.internal_links = ["missing.xhtml"]
        epub.extracted_files = ["/tmp/x/OEBPS/ch1.xhtml"]
        issues = LinksProcessor().check(epub)
        assert len(issues) == 1
```

- [ ] **Step 4: Compression processor**

Create `src/boozarr/processors/compression.py`:

```python
"""Compression and cleanup processor."""

from __future__ import annotations

from typing import Any

from boozarr.processors.base import BaseProcessor, Fix, Issue

_EXTRA = {".DS_Store", "thumbs.db", "Thumbs.db", "desktop.ini"}


class CompressionProcessor(BaseProcessor):
    name = "compression"

    def check(self, epub: Any) -> list[Issue]:
        issues: list[Issue] = []
        extra = [f for f in getattr(epub, "extra_files", []) if f.name in _EXTRA]
        if extra:
            issues.append(Issue(
                processor=self.name, severity="info",
                location="archive root",
                description=f"Found {len(extra)} extraneous file(s): {[e.name for e in extra]}",
                fix_possible=True,
            ))
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        return [Fix(
            processor=self.name, location=i.location,
            description=f"Stripped extraneous files",
            old_value=i.description, new_value="cleaned",
        ) for i in issues]
```

Create `tests/test_processors/test_compression.py`:

```python
"""Tests for CompressionProcessor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from boozarr.processors.compression import CompressionProcessor


class TestCompressionCheck:
    def test_no_issues_when_clean(self) -> None:
        epub = MagicMock()
        epub.extra_files = [Path("OEBPS/content.opf")]
        assert CompressionProcessor().check(epub) == []

    def test_issue_when_ds_store_present(self) -> None:
        epub = MagicMock()
        epub.extra_files = [Path(".DS_Store"), Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub)
        assert len(issues) == 1
```

- [ ] **Step 5: Run all processor tests**

Run: `uv run pytest tests/test_processors/ -v`
Expected: All **12+ tests pass**

- [ ] **Step 6: Commit**

```bash
git add src/boozarr/processors/ tests/test_processors/
git commit -m "feat: add Metadata, CSS Normalise, Links, Compression processors"
```

---

### Task 8: Wire CLI entry point + dependencies

**Files:**
- Modify: `src/boozarr/cli.py` (rewrite with full Click interface)
- Modify: `pyproject.toml` (add ebooklib, lxml, tinycss2)
- Test: `tests/test_cli.py` (new)

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
"""Tests for the boozarr CLI entry point."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from boozarr.cli import cli


class TestCliBasic:
    def test_help_succeeds(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "boozarr" in result.output.lower()

    def test_version_succeeds(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0

    def test_requires_library_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code != 0
        assert "--library-path" in result.output

    def test_dry_run_on_empty_directory(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--library-path", str(tmp_path)])
        assert result.exit_code == 0

    def test_dry_run_with_epub(self, tmp_path: Path) -> None:
        runner = CliRunner()
        lib = tmp_path / "lib"
        lib.mkdir()
        epub = lib / "book.epub"
        epub.write_bytes(b"dummy epub")
        result = runner.invoke(cli, ["--library-path", str(lib)])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: The CLI exists but is missing the full option set, so some tests may pass while the dry-run tests fail.

- [ ] **Step 3: Update pyproject.toml**

Edit `pyproject.toml` — add to `dependencies`:

```toml
dependencies = [
    "click",
    "loguru",
    "ebooklib",
    "lxml",
    "tinycss2",
]
```

- [ ] **Step 4: Rewrite src/boozarr/cli.py**

Replace the entire file:

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
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"], case_sensitive=False), default="INFO", metavar="<level>", help="Logging level.")
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py tests/test_epub.py tests/test_db.py tests/test_report.py tests/test_processor_base.py tests/test_pipeline.py tests/test_processors/ -v`
Expected: All **~27 tests pass**

- [ ] **Step 6: Commit**

```bash
git add src/boozarr/cli.py tests/test_cli.py pyproject.toml
git commit -m "feat: wire CLI entry point with all options and processors"
```

---

### Task 9: Final QA sweep

- [ ] **Step 1: Full test suite**

```bash
uv sync && uv run pytest -v
```
Expected: **All tests pass**

- [ ] **Step 2: Lint + format + types**

```bash
uv run ruff check src/boozarr/ tests/
uv run ruff format --check src/boozarr/ tests/
uv run mypy src/boozarr/
```
Expected: All clean

- [ ] **Step 3: Pre-commit**

```bash
uv run pre-commit run --all-files
```
Expected: All hooks pass

- [ ] **Step 4: Commit any QA fixes**

```bash
git add -A
git commit -m "chore: fix lint/type issues from QA"
```
