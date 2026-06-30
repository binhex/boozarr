# Enhanced Chapter Detection Design

> **Created:** 2026-06-30

## Goal

Improve the chapters processor so it detects **all** chapter markers in every
XHTML file (not just the first), and falls back to the spine reading order
when no text-based chapter markers exist at all.

## Problem

`_discover_chapters` currently finds only the **first** match per XHTML file:

```python
for pattern in _CHAPTER_PATTERNS:
    match = pattern.search(content)
    if match:
        discovered.append((rel_path, match.group(0)))
        break
```

A 128-chapter EPUB split across 4 files yields 4 entries, not 128.  The
break-after-first-match logic discards all remaining markers in the file.

Additionally, EPUBs with no text markers at all (Bourne books, Twilight
series, calibre TXT conversions) get zero entries even though their spine
has 8–40 content files with clear reading order.

## Design

### Enhancement 1: Multi-match discovery

Instead of per-pattern `search()` + `break`, use `finditer()` to collect
**every** match across all patterns in every file.  All matches are
collected, deduplicated by position, and sorted by spine order then
match position within each file.

All four patterns are tried in order, but the first pattern to match does
**not** stop processing — subsequent patterns continue scanning and all
distinct matches are included.

**Example:** A file with both "CHAPTER 1" and "Part 2" gets two entries.
A file with "CHAPTER 1" at position 500 and "Chapter 1" (case variation of
the same pattern) at position 500 is deduplicated to one entry.

**h1/h2 fallback:** The heading fallback only activates when **no** pattern
matched in that specific file.

**Sorting:** Results are sorted by spine reading order (expensive but
correct when files follow a naming convention).  When the OPF path is not
available (e.g. it's not in the extract dir), results are sorted by file
path alphabetically — which works for most calibre-generated EPUBs.

**Performance:** `finditer()` scans the entire file content once per
pattern.  For a typical EPUB (4 files × ~200KB each) this is negligible.
A 5000-file library processed through this path adds < 1 second total.

### Enhancement 2: Spine-based fallback

When `_discover_chapters` finds **zero** matches across the entire EPUB,
a new fallback method `_discover_from_spine(extract_dir, opf_path)` uses
the OPF spine to generate chapter entries.

**Algorithm:**

1. Parse the OPF XML to build `{id: href}` from `<manifest>` items
2. Parse `<spine>` to get the ordered list of `<itemref idref="...">`
3. Resolve each `idref` to its `href` via the manifest
4. Filter out non-content files using smart heuristics
5. Label each remaining file by extracting digits from its filename stem
6. Return the list of `(file_path, label)` pairs

**Smart heuristics for filtering non-content files:**

A file is skipped when its `href`, `id`, or filename stem (lowercased)
contains any of these substrings:

- `cover`, `title`, `toc`, `nav`, `copyright`, `about`

Or when the file is smaller than 2KB on disk.

Any reference in the spine whose `href` does not resolve to an existing
file in the extract directory is silently skipped.

**Filename-based labels:**

Extract trailing digits from the filename stem, then convert to a
human-readable label:

| Filename stem | Label |
|---------------|-------|
| `temp_calibre_txt_input_to_html_split_005` | "Chapter 5" |
| `part0007` | "Chapter 7" |
| `05_c1` | "Chapter 1" |
| `index_split_000` | "Index split 0" |
| `chapter_3` | "Chapter 3" |
| `story` (no digits) | "Story" |

The label extraction logic:
1. Strip the extension to get the stem
2. Find the last group of digits in the stem
3. If digits found, convert to int and produce "Chapter N" (strips
   leading zeros)
4. If no digits, use the stem as-is with underscores replaced by spaces
   and title-cased

## Method signature changes

| Method | Current | New |
|--------|---------|-----|
| `_discover_chapters` | `(extract_dir: Path)` | `(extract_dir: Path, opf_path: str | None)` |
| `_discover_from_spine` | *(doesn't exist)* | `(extract_dir: Path, opf_path: str)` |

`_discover_from_spine` is only called when `_discover_chapters` returns an
empty list and `opf_path` is provided.

The caller (`fix()`) already has `epub` and `extract_dir`.  It retrieves
the OPF path via `epub.get_opf_path()` and passes it through.

## Error handling

| Scenario | Behavior |
|----------|----------|
| Corrupt/missing OPF XML | `_discover_from_spine` returns `[]` (empty — NCX stays as-is) |
| Missing `<spine>` in OPF | Returns `[]` |
| idref not found in manifest | Skip that itemref, continue |
| href resolves to nonexistent file | Skip that item, continue |
| All spine items filtered out | Returns `[]` |
| Pattern finds zero matches, OPF path unavailable | Returns `[]` (spine fallback skipped) |

In all error cases the NCX is left untouched — no partial or malformed
entries are written.

## What stays unchanged

- `_CHAPTER_PATTERNS` list — same four patterns
- `_write_ncx()` — same NCX generation logic
- `check()` — same entry-point signature and behavior (still detects
  empty NCX correctly)
- All other processors — no changes
- `_find_ncx_path()` — same logic

## Testing strategy

### Category 1 tests (multi-match discovery)

- EPUB with 4 XHTML files, each containing 30+ "CHAPTER N" markers
  → verify 128 entries discovered
- EPUB with mixed patterns ("Chapter 1", "Part I", "Section 1")
  → verify all distinct matches collected
- EPUB with overlapping patterns ("CHAPTER 1" matching both
  `Chapter\s+\d+` and `CHAPTER\s+\w+`) → verify dedup to 1 entry
- EPUB with no text patterns but h1 headings → verify h1 fallback
  still works per file
- EPUB with no text patterns and no headings → verify empty return
  (spine fallback candidate)

### Category 2 tests (spine fallback)

- EPUB with zero text markers but 8 spine items → verify 5–6 content
  items discovered (covers/boilerplate filtered out)
- EPUB with corrupt OPF → verify empty return, no crash
- EPUB with valid OPF but missing `<spine>` → verify empty return
- EPUB where all spine items are filtered (only cover/toc/title)
  → verify empty return

### Integration tests

- Bourne Identity EPUB (empty NCX, no chapter text) → `--fix` writes
  NCX with spine-derived entries
- Digital Fortress EPUB (empty NCX, 128 chapter markers) → `--fix`
  writes NCX with 128 entries
- Rerun on same file → `_should_skip` returns True (NCX now has
  entries + config hash matches)

## Files changed

| File | Change |
|------|--------|
| `src/boozarr/processors/chapters.py` | `_discover_chapters` rewritten for multi-match; new `_discover_from_spine`, new `_label_from_filename` helpers |

| `tests/test_chapters_processor.py` | New test cases for multi-match and spine fallback |
| `tests/test_data/` | New multi-chapter and no-marker test EPUB fixtures |
