# `--compress` CLI Option Design

> **Created:** 2026-06-20

## Goal

Add a `--compress` CLI option that applies EPUB recompression when specified,
and is a no-op when omitted.  Follows the existing "auto-activate when
configured" pattern used by `BordersProcessor` and `CssNormaliseProcessor`.

## CLI

Add one new option to `boozarr/cli.py`:

```python
@click.option(
    "--compress",
    type=int,
    default=None,
    metavar="<0-9>",
    help="Apply EPUB recompression (0=store, 9=best).",
)
```

Stored in `config["compress"]` as `int | None`.  `None` (the default) means
"no compression requested".

## CompressionProcessor

### `check(epub, config=None)` — conditional activation

- When `config.get("compress")` is `None` → return `[]` (no-op).
- When set → scan for extraneous files (`.DS_Store`, `thumbs.db`,
  `desktop.ini` — existing behaviour).  Report one issue per file found.

### `fix(epub, issues, config)` — set compression level

- Returns a `Fix` for each extraneous file found (same as today).
- Sets `epub._compress_level = config["compress"]` on the EPUB wrapper so the
  Pipeline can read it during repack.

## Pipeline

`process_epub()` already calls `wrapper.repack(tmp_path)`.  The `EpubWrapper.repack()`
method currently creates a `ZipFile` with default compression:

```python
with zipfile.ZipFile(dst, "w") as zf:
```

Change to read the compress level if set:

```python
level = getattr(self, "_compress_level", None)
with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
```

Pass `level=None` when `_compress_level` is unset — Python then uses its
internal default (usually 6).

## Other processors

No changes.  The existing `CompressionProcessor` always runs; this change makes
it conditional like the other processors.

## Tests

- `test_no_issues_when_compress_not_set` — passes `config={}`, expects zero issues.
- `test_issues_when_compress_set` — passes `config={"compress": 9}`, expects
  extraneous-file issues.
- `test_fix_sets_compress_level` — verifies `epub._compress_level` is set by `fix()`.
- `test_compress_level_passed_to_repack` — integration test that verifies the
  compression level is threaded through to `ZipFile`.

## Files changed

| File | Change |
|------|--------|
| `src/boozarr/cli.py` | Add `--compress` Click option and config key |
| `src/boozarr/processors/compression.py` | `check()` gates on `config.get("compress")`; `fix()` sets `_compress_level` |
| `src/boozarr/epub.py` | `repack()` reads `_compress_level` and passes to `ZipFile` |
| `tests/test_processors/test_compression.py` | New/updated tests |
| `README.md` | Add `--compress` to options table |
