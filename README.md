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
- **Cross-device compatibility** — strips embedded fonts (`.otf`, `.ttf`, `.woff`,
  `.eot`, `.svg`), removes Apple Books display options, normalises OPF namespace
  prefixes, and cleans up orphaned `@font-face` CSS rules. WOFF2 fonts are
  preserved for EPUB3 readers.

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

### Shell completion (recommended)

Enable tab completion for all boozarr options:

```bash
# Bash — add to ~/.bashrc:
eval "$(_BOOZARR_COMPLETE=bash_source boozarr)"

# Zsh — add to ~/.zshrc:
eval "$(_BOOZARR_COMPLETE=zsh_source boozarr)"

# Fish — add to ~/.config/fish/completions/boozarr.fish:
_BOOZARR_COMPLETE=fish_source boozarr | source
```

Once enabled, `boozarr --lib` + **Tab** → `boozarr --library-path`, `boozarr --mar` + **Tab** cycles through `--margin`, `--margin-top`, etc.

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
| `--border` | — | Target border value (only applied when specified) |
| `--margin` | — | Target margin value (only applied when specified) |
| `--padding` | — | Target padding value (only applied when specified) |
| `--margin-top` | — | Target margin-top, px (only applied when specified) |
| `--margin-bottom` | — | Target margin-bottom, px (only applied when specified) |
| `--margin-left` | — | Target margin-left, px (only applied when specified) |
| `--margin-right` | — | Target margin-right, px (only applied when specified) |
| `--padding-top` | — | Target padding-top, px (only applied when specified) |
| `--padding-bottom` | — | Target padding-bottom, px (only applied when specified) |
| `--padding-left` | — | Target padding-left, px (only applied when specified) |
| `--padding-right` | — | Target padding-right, px (only applied when specified) |
| `--font-size` | 14 | Target base font size (only applied when specified) |
| `--line-height` | 1.2 | Target line height (only applied when specified) |
| `--text-indent` | 0 | Target text indent, px (only applied when specified) |
| `--paragraph-spacing` | — | Target paragraph spacing (only applied when specified) |
| `--text-align` | left | Target text-align (left, center, right, justify) |
| `--check-external-links` | off | Report external URLs (no validation in batch mode) |
| `--normalise` | off | Apply CSS defaults + cross-device compat (strip fonts, normalise OPF) |
| `--cleanup` | off | Remove empty `<p>`, `<div>`, `<span>` elements from XHTML |
| `--compress` | — | Apply EPUB recompression level (0=store, 9=best, only when specified) |

## How it works

For each EPUB file in the library:

1. **EpubWrapper** validates the ZIP structure and extracts to a temp directory.
2. Each enabled processor runs `check()` against the extracted EPUB, reporting issues.
3. If `--fix` is set, enabled processors apply their fixes.
4. The modified EPUB is re-packed with compression.
5. A result is logged per-file: `[OK]`, `[MODIFY]`, `[ERR]`, or `[SKIP]`.

Unchanged files are skipped on re-run (tracked by SHA-256 hash and CLI config hash in SQLite).

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
