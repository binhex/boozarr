# Chapter Detection v2 Design

> **Created:** 2026-07-02

## Goal

Fix three gaps in the chapters processor exposed by a calibre-converted EPUB
(Stephen King — "1408") where chapters exist but boozarr reports 0 issues:

1. `check()` gives a false negative when the NCX has only placeholder navPoints
2. Content files with `.html` extension are never scanned
3. No pattern matches chapter markers that are bare numbers or Roman numerals
   inside heading tags

## Problem

**Gap 1 — check() false negative.** The NCX has one `<navPoint>` ("Start" →
titlepage.xhtml) and `check()` treats this as valid — it only checks whether
*any* navPoint exists, not whether they represent real chapters.

**Gap 2 — missing `.html` scan.** `_discover_chapters` globs `*.xhtml` only.
Calibre-converted EPUBs often use `.html` extensions for content files (while
correctly declaring `application/xhtml+xml` media-type in the OPF manifest).
These files are invisible to the discovery loop.

**Gap 3 — bare numbers/Roman numerals in headings.** The current
`_CHAPTER_PATTERNS` list covers prefixed patterns (`Chapter 1`, `Part II`)
and the h1/h2 fallback catches heading content as plain text.  But there is
no explicit pattern for bare chapter numbers inside heading tags:

```html
<h2 class="calibre2">I</h2>       <!-- Roman numeral -->
<h2 class="calibre2">1</h2>       <!-- plain number -->
```

These are currently caught only by the h1/h2 fallback (when Gap 2 doesn't
block them).  An explicit pattern makes the detection intentional rather than
implicit.

## Design

### Enhancement 1: Smarter `check()` — filter placeholder navPoints

New helper `_has_real_chapters(ncx_root)`:

- Iterates all `<navPoint>` elements in the NCX
- Extracts the `src` attribute from each `<content>` child
- Uses the existing `_should_skip_content_file()` on the filename stem to
  discard entries pointing to cover, titlepage, toc, nav, copyright, or
  about pages
- Returns `True` only when at least one navPoint survives filtering

`check()` calls this instead of `findall("ns:navPoint")`.  An NCX with only
a "Start → titlepage.xhtml" entry now correctly reports missing chapters.

### Enhancement 2: Scan `.html` files

The glob in `_discover_chapters` changes from:

```python
extract_dir.rglob("*.xhtml")
```

to:

```python
extract_dir.rglob("*.[xh]tml")
```

This catches both `.html` and `.xhtml` content files in a single pass.

### Enhancement 3: Bare number/Roman heading pattern

A new pattern is appended to `_CHAPTER_PATTERNS`:

```python
re.compile(r"<h[1-6][^>]*>\s*(\d+|[IVXLCDM]+)\s*</h[1-6]>", re.IGNORECASE)
```

This matches heading tags whose sole text content is a number or Roman
numeral.  Examples:

| Heading | Label |
|---------|-------|
| `<h2>I</h2>` | `I` |
| `<h2>1</h2>` | `1` |
| `<h3>XIV</h3>` | `XIV` |
| `<h1>42</h1>` | `42` |

The label is the raw heading text — no conversion to Arabic numerals.  The
h1/h2 fallback at the end of `_scan_file_for_chapters` still serves as a
safety net for headings whose content is neither a number nor Roman numeral.

### Existing patterns — no changes

The four existing patterns continue to work as before.  The new pattern is
appended after them and runs the same `finditer()` loop:

```
Chapter\s+\d+           → catches Chapter 1, CHAPTER 42
Part\s+\d+              → catches Part 1, part 3
Section\s+\d+           → catches Section 1
CHAPTER\s+\w+           → catches CHAPTER ONE
<h1-6>\d+\|[IVXLCDM]+\b → catches <h2>II</h2>, <h1>3</h1>  [NEW]
```

### Labels — raw text as-is

No label transformation.  `finditer()` returns `match.group(0)` as before,
which for the new pattern is the full heading tag content (e.g. `II`, `1`).

### Files changed

| File | Changes |
|------|---------|
| `src/boozarr/processors/chapters.py` | Add `_has_real_chapters()`, modify `check()`, change glob, add heading-number pattern |
| `tests/test_processors/test_chapters.py` | Add test cases |

## Error Handling

| Scenario | Behavior |
|----------|----------|
| NCX XML parse fails | Return `[]` — unclear NCX is not fixable |
| navPoint has no `<content>` child | Skip that navPoint |
| Corrupt XHTML file on read | Skip that file, continue scanning |
| `<h2>MCMXCIX</h2>` (valid but absurd numeral) | Matched — pattern is structural, not semantic |
| `<h2>Introduction</h2>` | Not matched by number pattern, caught by h1/h2 fallback |
| `<p>Henry VIII edition</p>` | Not matched — not inside heading tag |
| `<h2>The year is 1942</h2>` | Not matched — heading contains text beyond just a number |

## Test Strategy

| Test case | What it verifies |
|-----------|-----------------|
| NCX with only "Start→titlepage" navPoint | `check()` returns `[Issue]` |
| NCX with titlepage + one real chapter navPoint | `check()` returns `[]` |
| EPUB with `.html` content file containing `Chapter 1` | Pattern detected |
| EPUB with `.xhtml` and `.html` mixed | Both scanned |
| XHTML with `<h2>IV</h2>` | New pattern matches, label = "IV" |
| XHTML with `<h1>3</h1>` | New pattern matches, label = "3" |
| XHTML with `<h2>Introduction</h2>` and no other patterns | h1/h2 fallback catches it |
| XHTML with `<h2>Henry VIII</h2>` and no other patterns | Number pattern NOT matched, h1/h2 fallback catches "Henry VIII" |
