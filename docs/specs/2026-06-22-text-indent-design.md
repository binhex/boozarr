# `--text-indent` CLI Option Design

> **Created:** 2026-06-22

## Goal

Add a `--text-indent` CLI option that controls paragraph first-line indentation.
When specified, the processor normalises `text-indent` in CSS to the user's
target value.  When omitted, the processor is a no-op.  Follows the existing
"auto-activate when configured" pattern.

## CLI

Single new option in `boozarr/cli.py`:

```python
@click.option(
    "--text-indent",
    type=int,
    default=None,
    is_flag=False,
    flag_value=0,
    metavar="<int>",
    help="Target text indent, px (no value = 0).",
)
```

| Scenario | `config["text_indent"]` | Result |
|----------|--------------------------|--------|
| Not passed | `None` | Processor skipped |
| `--text-indent` | `0` (flag_value) | Indent set to `0px` |
| `--text-indent 20` | `20` | Indent set to `20px` |

Stored in `config["text_indent"]`.

## `--normalise` integration

`--text-indent` is part of the `--normalise` flag. When `--normalise` is
passed and `--text-indent` is not explicitly set, it defaults to `0`:

```python
defaults = {
    # ... other defaults ...
    "text_indent": 0,
}
```

This means `--normalise` alone sets `text-indent` to `0`, removing all
paragraph indentation — consistent with the other CSS defaults applied by
`--normalise`.

## CssNormaliseProcessor

### `_PARAGRAPH_PROPS`

Added `"text-indent"` to the property list so it is scanned during CSS
collection.

### `_build_target_map`

When `config["text_indent"]` is not `None`, the target map includes
`"text-indent"` with the normalised value (via `normalize_css_value`, which
appends `px` to bare integers).

### CSS collection and rewrite

`text-indent` values are collected from CSS files and inline `<style>` blocks
via the existing `_parse_css_text` / `_scan_xhtml_styles` infrastructure.
Rewriting uses the same `_rewrite_css_text` / `_rewrite_css_file` /
`_rewrite_inline_styles` pipeline as the other paragraph-level properties.

## Other processors

No changes.

## Tests

Existing processor tests cover the new property by exercising the full
`check()` → `fix()` pipeline with `text_indent` in the config dict.

## Files changed

| File | Change |
|------|--------|
| `src/boozarr/cli.py` | Add `--text-indent` Click option, parameter, config key, `--normalise` default |
| `src/boozarr/processors/css_normalise.py` | Add `text-indent` to `_PARAGRAPH_PROPS` and `_build_target_map` |
