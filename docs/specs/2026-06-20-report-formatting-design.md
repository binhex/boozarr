# Report Formatting Redesign

## Overview

Improve the boozarr CLI output to show old→new values in fix details and
present the summary as a clean table-style footer.

**Status:** Design approved 2026-06-20

## Motivation

The current output shows generic "Normalised CSS (padding)" without indicating
what the value was or what it changed to. The summary uses inconsistent spacing
and is hard to scan quickly.

## Output Format

### Per-file fix details (inline arrow format)

Each fix detail line shows the property and the old→new transition:

```
[WARN]   test.epub — 5 issues, 0 fixes (dry-run)
         - borders: border 5px → 1px
         - borders: margin 3cm → 1em
         - borders: padding 5px → 10px
         - css_normalise: font-size 2em → 1em
```

Format: `{processor}: {property} {old_value} → {new_value}`

When the old and new values are identical: `{processor}: {property} {value} == {value}`

### Summary footer (table-style)

```
────────────────────────────────────────
  Files processed:  1  (0 skipped, 0 errors)
  Issues found:     7
  Fixes applied:    0

  Fixes by processor:
    borders          5   border 5px→1px, margin 3cm→1em
    css_normalise    2   font-size 2em→1em, line-height 2→1.5
────────────────────────────────────────
  Duration: 0.1s
```

- Divider line (─ characters) creates a clear visual boundary
- Left-aligned labels, right-aligned values for scannability
- Processor breakdown line includes comma-separated change summaries
- In fix mode, "(dry-run)" is replaced by actual fix count and no suffix

### Dry-run vs fix mode

| Aspect | Dry-run | Fix mode |
|--------|---------|----------|
| Per-file suffix | `(dry-run)` | none |
| Fix details shown | yes (preview) | yes (actual) |
| Fixes applied count | `0` | actual count |
| "Fixes by processor" shown | yes | yes |

## Implementation

### Changes required

| File | Change |
|------|--------|
| `src/boozarr/processors/borders.py` | Populate `Fix(old_value=issue_property_value, new_value=target)` when creating Fix objects |
| `src/boozarr/processors/css_normalise.py` | Same as borders |
| `src/boozarr/pipeline.py` | Format `fix_details` string as `"{proc.name}: {prop} {old} → {new}"` using `Fix.old_value`/`new_value` |
| `src/boozarr/report.py` | Rewrite `final_summary()` with table-style layout, dividers, aligned columns. Include change summaries in processor breakdown. |
| `src/boozarr/processors/base.py` | No changes needed — `Fix` dataclass already has `old_value`/`new_value` fields |

### Data flow

1. `BordersProcessor.fix()` creates `Fix(old_value="5px", new_value="1px", ...)`
2. `Pipeline._run_processors()` iterates fixes, formats: `"borders: border 5px → 1px"`
3. `Report.log_line()` stores `fix_details` list, appends to per-file output
4. `Report.final_summary()` produces table-style summary with processor breakdown

### Edge cases

- **Same old/new values:** Show `==` instead of `→` to indicate no effective change
- **Zero issues:** Summary shows `Issues found: 0`, no processor breakdown
- **All files skipped:** Summary shows `Files processed: N (N skipped, 0 errors)`
- **No processor breakdown data:** Omit "Fixes by processor" section entirely

## Non-goals

- No changes to DB schema
- No new CLI flags
- No changes to per-file `[WARN]`/`[OK]`/`[SKIP]`/`[ERR]` tags
