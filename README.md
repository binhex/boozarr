# boozarr

Automated EPUB editor — batch checks and fixes for EPUB libraries at scale.

Processes a library of EPUB files (500–5000+) running a configurable pipeline of checks and fixes to normalise and improve EPUB quality.

## Features

- **Chapter detection** — Detects missing or empty chapter tables of contents. Scans XHTML content for heading patterns and injects chapter markers into `toc.ncx` / `nav.xhtml`.
- **CSS border/margin normalisation** — Scans all CSS for border, margin, and padding properties. Flags values that differ from configurable targets and normalises them.
- **Missing metadata fixer** — Reads OPF `<metadata>` and infers `dc:title`, `dc:creator`, `dc:language`, and `dc:date` from filenames when absent.
- **CSS formatting normalisation** — Detects non-standard font-size, line-height, text-align, and margin values on paragraph-level elements.
- **Broken link checker** — Verifies internal `href` targets exist within the EPUB. Optionally validates external URLs.
- **Compression and cleanup** — Strips extraneous files (`.DS_Store`, `thumbs.db`) and re-packs with optimal compression.

## Prerequisites

- [Python 3.12+](https://www.python.org/downloads/)
- [Astral uv](https://github.com/astral-sh/uv#installation)

## Installation

```bash
git clone https://github.com/binhex/boozarr
cd boozarr
uv venv --quiet
uv sync
```

## Usage

Run in dry-run mode (check-only, no modifications):

```bash
boozarr --library-path /path/to/epub/library
```

Apply fixes:

```bash
boozarr --library-path /path/to/epub/library --fix
```

Backups are created automatically (on by default). Disable with:

```bash
boozarr --library-path /path/to/epub/library --fix --no-backup
```

Skip specific processors:

```bash
boozarr --library-path /path/to/epub/library --skip-chapters --skip-links
```

Customise CSS targets:

```bash
boozarr --library-path /path/to/epub/library --border 1px --margin 0 --padding 0
```

### All options

| Flag | Default | Description |
|------|---------|-------------|
| `--library-path` | *required* | Directory containing EPUB files to process (recursive scan) |
| `--fix` | off | Apply fixes; default is dry-run (check-only) |
| `--no-backup` | off | Disable automatic `.bak` backups (on by default) |
| `--db-path` | `<project>/db/boozarr.db` | SQLite database for tracking processed files |
| `--log-path` | `<project>/logs/boozarr.log` | Log file path |
| `--log-level` | `INFO` | Logging level (DEBUG, INFO, SUCCESS, WARNING, ERROR) |
| `--skip-chapters` | off | Skip chapter detection and ToC injection |
| `--skip-borders` | off | Skip CSS border/margin normalisation |
| `--skip-metadata` | off | Skip missing metadata fixer |
| `--skip-css` | off | Skip CSS formatting normalisation |
| `--skip-links` | off | Skip broken link checker |
| `--no-compress` | off | Skip compression and cleanup |
| `--border` | `none` | Target border value |
| `--margin` | `1em` | Target margin value |
| `--padding` | `0` | Target padding value |
| `--font-size` | `1em` | Target base font size |
| `--line-height` | `1.5` | Target line height |
| `--paragraph-spacing` | `1em` | Target paragraph spacing |
| `--check-external-links` | off | Validate external URLs via HEAD requests |

## How it works

For each EPUB file in the library:

1. **EpubWrapper** validates the ZIP structure and extracts to a temp directory.
2. Each enabled processor runs `check()` against the extracted EPUB, reporting issues.
3. If `--fix` is set, enabled processors apply their fixes.
4. The modified EPUB is re-packed with compression.
5. A result is logged per-file: `[OK]`, `[WARN]`, `[ERR]`, or `[SKIP]`.

Unchanged files are skipped on re-run (tracked by SHA-256 hash in SQLite).

## Development

```bash
git clone https://github.com/binhex/boozarr
cd boozarr
uv venv --quiet
uv sync --extra dev
```

Run tests:

```bash
uv run pytest -v
```

Lint and type-check:

```bash
uv run ruff check src/boozarr/ tests/
uv run mypy src/boozarr/
```

Pre-commit (run before committing):

```bash
uv run pre-commit run --all-files
```

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
