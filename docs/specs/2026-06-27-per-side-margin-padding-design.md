# Per-side margin/padding CLI options

> **Created:** 2026-06-27

## Goal

Add individual `--margin-top`, `--margin-bottom`, `--margin-left`,
`--margin-right` options (and the equivalent padding set) so users can
control spacing per side without being forced to use the `--margin` /
`--padding` shorthand.  The shorthand options are kept as conveniences.

## CLI — 10 new options

All follow the existing `flag_value` / `default=None` auto-activate pattern:

```
--margin-top <int>        Target margin-top, px (no value = 2)
--margin-bottom <int>     Target margin-bottom, px (no value = 2)
--margin-left <int>       Target margin-left, px (no value = 2)
--margin-right <int>      Target margin-right, px (no value = 2)

--padding-top <int>       Target padding-top, px (no value = 2)
--padding-bottom <int>    Target padding-bottom, px (no value = 2)
--padding-left <int>      Target padding-left, px (no value = 2)
--padding-right <int>     Target padding-right, px (no value = 2)
```

Config keys: `margin_top`, `margin_bottom`, `margin_left`, `margin_right`,
`padding_top`, `padding_bottom`, `padding_left`, `padding_right`.

### Interaction with `--margin` and `--padding`

The shorthand options already expand to all four sides (plus
`margin-top`/`margin-bottom` since an earlier addition).  The new per-side
options are applied **after** the shorthand, so explicit sides override:

```
--margin 5 --margin-top 10
  → target_map = {margin: 5px, margin-top: 10px, margin-left: 5px, ...}

--margin-top 10 (no --margin)
  → target_map = {margin-top: 10px}
```

## `_build_target_map` (borders.py)

The existing `margin_val` block already expands to all sides.  New blocks
are added for the per-side config keys, applied after the shorthand so
they take priority:

```python
# shorthand
margin_val = config.get("margin")
if margin_val is not None:
    target_map["margin"] = ...
    target_map["margin-top"] = ...
    ...

# per-side overrides
margin_top = config.get("margin_top")
if margin_top is not None:
    target_map["margin-top"] = normalize_css_value(margin_top)
# ... same for each of the 8 sides
```

## `--normalise` integration

`--normalise` sets all 8 side defaults to `2`.  Per-side overrides work
as expected: `--normalise --margin-top 10` sets top to 10 and everything
else to 2.

## Other processors

No changes.  `_TARGET` already includes all margin and padding properties.

## Files changed

| File | Change |
|------|--------|
| `src/boozarr/cli.py` | 10 new Click options, params, config keys, normalise defaults |
| `src/boozarr/processors/borders.py` | `_build_target_map` reads per-side config keys |
| `README.md` | Options table updated |
