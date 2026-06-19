# EPUB Automated Editor — Design Spec

**Date:** 2026-06-19
**Status:** Draft
**Author:** Investigation / Design

## Overview

An automated CLI tool written in Python that processes a library of EPUB files,
running a configurable pipeline of checks and fixes to normalise and improve
EPUB quality at scale. Designed for large archives (500–5000+ EPUBs) with
mixed content types.

## CLI Interface

### Usage

```bash
boozarr --library-path <DIR> [OPTIONS]
```

- **`--library-path`** (required): Path to the directory containing EPUB files
  to process. The tool scans this directory recursively for `.epub` files.

- **`--fix`** (flag): By default the tool runs in **dry-run mode** — it
  checks and reports issues but makes no changes. Pass `--fix` to apply fixes.

- **`--backup`** (flag): Create `.bak` copies of each EPUB (same directory,
  `.epub.bak` extension) before modifying. Compatible with `--fix`.

- **`--db-path`** (default: `./boozarr.db`): Path to the SQLite database
  used to track processed files and avoid re-processing unchanged EPUBs.

- **`--log-path`** (default: `./boozarr.log`): Path to the log file.

### Feature Toggles (enable/disable individual processors)

All processors are enabled by default. Use `--skip-*` to disable:

| Flag | Disables |
|------|----------|
| `--skip-chapters` | Chapter detection & ToC injection |
| `--skip-borders` | CSS border/margin normalisation |
| `--skip-metadata` | Missing metadata fixer |
| `--skip-css` | CSS formatting normalisation |
| `--skip-links` | Broken link checker |
| `--no-compress` | Compression & cleanup optimisation |

### Processor-Specific Options

| Flag | Default | Applies to |
|------|---------|------------|
| `--border` | `none` | Target border value |
| `--margin` | `1em` | Target page/content margin |
| `--padding` | `0` | Target padding value |
| `--font-size` | `1em` | Target base font size |
| `--line-height` | `1.5` | Target line height |
| `--paragraph-spacing` | `1em` | Target paragraph spacing |
| `--check-external-links` | (flag) | Enable external URL validation via HEAD requests |

## Architecture

### Project Structure

```
boozarr/
├── cli.py               # Click CLI entry point, argument parsing
├── pipeline.py          # Pipeline orchestrator — runs processors in sequence
├── epub.py              # EpubWrapper — unzip, inspect, manipulate, repack
├── db.py                # SQLite database — tracking & audit trail
├── report.py            # Console summary reporting
├── processors/
│   ├── __init__.py
│   ├── base.py          # BaseProcessor abstract class
│   ├── chapters.py      # Chapter detection & ToC injection
│   ├── borders.py       # CSS border/margin/padding normalisation
│   ├── metadata.py      # Missing metadata fixer
│   ├── css_normalise.py # Font/line-height/paragraph standardisation
│   ├── links.py         # Broken link checker
│   └── compression.py   # EPUB re-compression & file cleanup
└── tests/
    ├── fixtures/        # Sample EPUBs for unit tests
    ├── test_processors/ # Unit tests per processor
    └── test_pipeline.py # Integration tests
```

### Pipeline Flow

```
─── (per EPUB file) ───

  1. EpubWrapper: validate ZIP, extract to temp dir
  2. For each enabled processor (in order):
       a. processor.check(epub) → list of Issue
       b. If --fix: processor.fix(epub, issues, config) → list of Fix
  3. EpubWrapper: repack (temp → final), clean up temp
  4. db.record(file_path, hash, status, issues, fixes)
  5. report.log_line(file, summary)
```

### BaseProcessor Interface

```python
class BaseProcessor(ABC):
    name: str  # e.g. "chapters", "borders"

    @abstractmethod
    def check(self, epub: EpubWrapper) -> list[Issue]:
        """Scan the EPUB and return detected issues."""
        ...

    @abstractmethod
    def fix(self, epub: EpubWrapper, issues: list[Issue], config: dict) -> list[Fix]:
        """Apply fixes for detected issues."""
        ...
```

- **`Issue`**: `{processor, severity, location, description, fix_possible}`
- **`Fix`**: `{processor, location, description, old_value, new_value}`

## Individual Processors

### 1. Chapters (`--skip-chapters`)

**Check:**
1. Read existing EPUB ToC (toc.ncx / nav.xhtml).
2. If present and populated with entries → no issues, skip.
3. If missing or empty → scan all XHTML content files for chapter markers.

**Heuristic detection (fallback when ToC missing):**
- Regex patterns: `Chapter \d+`, `Part \d+`, `Section \d+`, `CHAPTER`, `PART`
- Roman numeral chapter markers (`IV`, `XII`, etc.)
- `<h1>` / `<h2>` heading tags
- Thematic breaks (`<hr/>`)
- CSS `page-break-before` / `page-break-after` properties
- Consecutive numbered patterns (heuristic voting)

**Fix:**
1. Insert `<a id="ch-N"/>` anchors at detected chapter start points.
2. Generate or update `toc.ncx` and `nav.xhtml` with chapter entries.
3. Update `content.opf` spine metadata if needed.

### 2. Borders & Margins (`--skip-borders`)

**Check:**
Scan all CSS (inline `<style>`, linked `.css` files, and inline `style="..."` attributes)
for properties: `border`, `border-width`, `border-style`, `border-color`,
`margin`, `margin-*`, `padding`, `padding-*`. Flag any value that differs from
the configured target.

**Fix:**
Replace every detected border/margin/padding value with the user-defined target.
Configurable via `--border`, `--margin`, `--padding`.

### 3. Missing Metadata (`--skip-metadata`)

**Check:**
Read OPF `<metadata>` section. Report missing: `dc:title`, `dc:creator`,
`dc:publisher`, `dc:date`, `dc:language`.

**Fix:**
- Attempt to infer from filename: parse `AuthorName - BookTitle.epub` patterns.
- For language, default to `en` if absent and unguessable.
- Write inferred values to OPF metadata section.

### 4. CSS Normalisation (`--skip-css`)

**Check:**
Scan CSS for `font-size`, `line-height`, `text-align`, margin/padding on
paragraph-level elements (`p`, `div`, `section`, `body`).

**Fix:**
Replace inconsistent values with configured targets (`--font-size`,
`--line-height`, `--paragraph-spacing`).

### 5. Link Checker (`--skip-links`)

**Check:**
- Parse all internal `href` attributes. Verify target files/anchor IDs exist in
  the EPUB.
- For external URLs: optional (controlled by `--check-external-links` flag),
  send HEAD requests and report broken links.

**Fix:**
- Report-only for broken external links.
- Optionally remove or comment out broken internal references (future).

### 6. Compression & Cleanup (`--no-compress`)

**Check:**
- Report current file count, compression ratio, presence of extraneous files.

**Fix:**
- Re-zip EPUB with optimal compression.
- Strip: `.DS_Store`, `thumbs.db`, `Thumbs.db`, `desktop.ini`.
- Remove empty directories.

## SQLite Database

### Schema

```sql
CREATE TABLE processed_files (
    file_path TEXT PRIMARY KEY,
    file_hash TEXT NOT NULL,            -- SHA-256 of original EPUB
    processed_at TEXT NOT NULL,         -- ISO 8601 timestamp
    status TEXT NOT NULL,               -- 'ok', 'errors', 'skipped'
    issues_found INTEGER DEFAULT 0,
    fixes_applied INTEGER DEFAULT 0,
    dry_run BOOLEAN NOT NULL            -- true = check-only, false = fixes applied
);

CREATE TABLE processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    processor TEXT NOT NULL,            -- e.g. 'chapters', 'borders'
    action TEXT NOT NULL,               -- 'check' or 'fix'
    detail TEXT,                        -- JSON blob describing findings/changes
    timestamp TEXT NOT NULL             -- ISO 8601 timestamp
);
```

### Behaviour

- Before processing a file, compute SHA-256 hash.
- If hash matches a `processed_files` record with status `ok` → skip file
  (fast re-runs).
- After processing, insert/update the record.
- All check and fix actions are logged to `processing_log`.

## Reporting

Per-file, printed as processing progresses:
```
[OK]   /path/to/book1.epub          — 0 issues, 3 fixes
[WARN] /path/to/book2.epub          — 2 issues (missing metadata), 0 fixes
[ERR]  /path/to/broken.epub         — corrupt ZIP, skipped
[SKIP] /path/to/book3.epub          — unchanged since last run
```

Final summary:
```
Processed: 147 files
  - Unchanged (skipped): 23
  - Issues found: 89 across 61 files
  - Fixes applied: 76
  - Errors: 3
Duration: 12.4s
```

## Error Handling

- **Per-EPUB isolation:** Failure in one EPUB → log error, continue to next.
  Never halts batch processing.
- **Per-processor isolation:** Each processor runs independently. If one
  crashes, subsequent processors still execute.
- **ZIP validation:** Before extraction, verify EPUB is a valid ZIP archive.
  Skip and report corrupt files.
- **Atomic writes:** Extract to temp dir, manipulate there, repack to a temp
  file, then rename over the original (or output location). If the tool
  crashes mid-process, the original is intact.
- **Backup:** When `--backup` is set, copy `.bak` before any modification.

## Testing Strategy

- **Unit tests per processor:** Each `check()` and `fix()` method tested
  against crafted sample EPUBs in `tests/fixtures/`.
- **Fixture categories:**
  - `no-chapters.epub` — narrative text without ToC
  - `messy-borders.epub` — inconsistent CSS border properties
  - `missing-metadata.epub` — no title/author in OPF
  - `corrupt.epub` — invalid ZIP structure
  - `mixed-styles.epub` — inline + linked CSS variations
- **Integration test:** Full pipeline run against a test library directory.
- **Tools:** `pytest`, `pytest-cov`, `ruff`, `mypy`.
- **Coverage target:** 80%+ per processor module.

## Dependencies

| Library | Purpose |
|---------|---------|
| `click` | CLI argument parsing |
| `ebooklib` | EPUB reading/writing (OPF, NCX, NAV, spine) |
| `lxml` | Fast XML/HTML parsing for XHTML, OPF, NCX |
| `tinycss2` | Parse and manipulate CSS |
| `loguru` | Structured logging |

> **Note:** `loguru` and `click` require user confirmation per AGENTS.md
> standards — already covered during this design process.

## Out of Scope (YAGNI)

- Parallel/multithreaded processing
- Web UI or daemon mode
- Plugin hot-reloading
- Integration with external book databases
- AI/ML-based chapter detection
- Calibre or other tool integration
- Ebook format conversion (mobi, azw3, pdf)

## Future Possibilities (Post-MVP)

- Multi-threaded processing for very large libraries (user-controlled thread count)
- Configuration file (`boozarr.toml`) for reusable processor settings
- Additional processors: image optimisation, font embedding checks,
  accessibility validation (alt text on images), ISBN lookup for metadata
