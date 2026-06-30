# Cross-Device Compatibility Processor — Design Spec

> **Created:** 2026-06-30

## Goal

Add a new `CompatProcessor` that strips embedded fonts, removes Apple-specific
metadata, normalises OPF namespace prefixes, and cleans up orphaned CSS
`@font-face` rules — all gated behind the existing `--normalise` flag.

## Motivation

Some EPUBs embed publisher-chosen fonts (`.otf`, `.ttf`, `.woff`) and use
Apple Books-specific metadata (`com.apple.ibooks.display-options.xml`).
These files cause rendering failures on non-Apple e-ink readers such as the
XTEINK X4, whose firmware does not support embedded fonts and has trouble
parsing namespace-prefixed OPF markup (`<ns0:itemref>`).

Stripping fonts and normalising the OPF produces a smaller, more broadly
compatible EPUB with no degradation on any reader — every mainstream reader
falls back to system fonts automatically when embedded fonts are missing.

## Design

### New processor: `CompatProcessor`

- File: `src/boozarr/processors/compat.py`
- Class: `CompatProcessor(BaseProcessor)`, `name = "compat"`
- Placed **first** in the pipeline order so downstream processors see a
  clean, standard-format EPUB
- Gated by the existing `--normalise` CLI flag (no new CLI options)

### Font stripping

**Formats removed** (OTF, TTF, WOFF, EOT, SVG):

| Media type | Extension |
|------------|-----------|
| `application/x-font-otf`, `font/otf` | `.otf` |
| `application/x-font-ttf`, `font/ttf` | `.ttf` |
| `application/font-woff` | `.woff` |
| `application/vnd.ms-fontobject` | `.eot` |
| `image/svg+xml` (only when in a `fonts/` path) | `.svg` |

**WOFF2 is preserved** — required by EPUB3 readers for web-style typography.

`check()` scans the OPF manifest for font `<item>` entries matching the
above media types and reports one `Issue` per file.  Also reports an issue
when `META-INF/com.apple.ibooks.display-options.xml` is present.

`fix()`:
1. Removes font files from the extracted archive.
2. Removes the corresponding `<item>` entries from the OPF `<manifest>`.
3. Removes `com.apple.ibooks.display-options.xml` from the archive and its
   `<item>` from the manifest (if present).
4. Strips `@font-face { ... }` blocks from CSS files whose `src:` URL
   references a removed font — prevents "missing resource" warnings in
   readers.

### OPF namespace normalisation

The OPF XML is rewritten so all namespace-prefixed element names
(`<ns0:itemref>`, `<ns0:item>`, `<ns0:spine>`, etc.) become bare tags.

1. Parse the OPF with namespace-aware XML (`ElementTree`).
2. Re-serialize with bare element names (no prefix).
3. Add `xmlns="http://www.idpf.org/2007/opf"` to the root `<package>`
   element if not already present.
4. Remove any existing `xmlns:ns0=...` prefix declarations.

Semantic meaning is preserved identically — the transformation is pure
namespace-resolution.

### Pipeline integration

CompatProcessor is inserted at position 0 in `_collect_processors()` in
`cli.py`.  It is **NOT** in the default processor list — the pipeline only
runs processors with a matching config key, so it activates only when
`--normalise` is set (which populates the config with CSS normalisation
targets).

No pipeline code changes needed — the existing `_run_processors` loop in
`pipeline.py` already handles per-processor activation via config presence.

### Error handling

| Scenario | Behavior |
|----------|----------|
| No embedded fonts present | `check()` returns `[]` |
| Corrupt/unreadable OPF | `check()` returns `[]`, `fix()` returns `[]` |
| Font file already absent from archive | `fix()` skips file removal, still cleans manifest |
| `@font-face` references missing/non-existent file | Skip that rule, continue |
| OPF already uses bare tags (no prefix) | Normalisation step is a no-op |
| CSS file unreadable | Skip that file, continue |

### CLI

No new CLI options.  `--normalise` already sets CSS defaults
(`_apply_normalise_defaults`).  We add a `"normalise": True` key to the
config dict so CompatProcessor can detect the flag.

## Testing strategy

### Unit tests

- Manifest scan with no font items → 0 issues
- Manifest scan with 3 font items + Apple display options → 4 issues
- Manifest scan with WOFF2 only → 0 issues (WOFF2 preserved)
- Font file removal from extract directory
- Manifest `<item>` removal after font deletion
- Apple display options file removal
- `@font-face` rule removal from CSS
- OPF namespace normalisation (ns0-prefixed → bare tags)
- OPF already bare → no-op
- Corrupt OPF → empty returns, no crash

### Integration tests

- Green Mile EPUB → verify fonts removed, OPF normalised, NCX intact
- EPUB with no embedded fonts → verify 0 issues, no modifications
- EPUB with WOFF2 only → verify WOFF2 preserved
- Rerun on already-processed EPUB → verify `_should_skip` works

## Files changed

| File | Change |
|------|--------|
| `src/boozarr/processors/compat.py` | **New** — CompatProcessor |
| `src/boozarr/cli.py` | Add CompatProcessor to `_collect_processors`, add `normalise: True` to config |
| `tests/test_processors/test_compat.py` | **New** — unit + integration tests |
| `README.md` | Update `--normalise` description to mention new compatibility features |
