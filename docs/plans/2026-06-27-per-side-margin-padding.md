# Per-side margin/padding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-side `--margin-top`, `--padding-left`, etc. CLI options that override the `--margin`/`--padding` shorthand.

**Architecture:** New config keys (`margin_top`, `padding_left`, etc.) are read in `_build_target_map` AFTER the shorthand expansion, so explicit sides take priority. CLI options follow the existing `flag_value=2, default=None` auto-activate pattern.

**Tech Stack:** Python 3.12, Click, pytest

---

### Task 1: BordersProcessor — per-side config keys

**Files:**
- Modify: `src/boozarr/processors/borders.py:178-195` (after padding expansion)

- [ ] **Step 1: Add per-side margin config reads**

After the existing `margin_val` block (which sets `margin`, `margin-left`, `margin-right`, `margin-top`, `margin-bottom`), add overrides for the individual sides:

```python
        # Per-side margin overrides
        for key, prop in [
            ("margin_top", "margin-top"),
            ("margin_bottom", "margin-bottom"),
            ("margin_left", "margin-left"),
            ("margin_right", "margin-right"),
        ]:
            val = config.get(key)
            if val is not None:
                target_map[prop] = normalize_css_value(val)
```

- [ ] **Step 2: Add per-side padding config reads**

Same pattern, after the existing `padding_val` block:

```python
        # Per-side padding overrides
        for key, prop in [
            ("padding_top", "padding-top"),
            ("padding_bottom", "padding-bottom"),
            ("padding_left", "padding-left"),
            ("padding_right", "padding-right"),
        ]:
            val = config.get(key)
            if val is not None:
                target_map[prop] = normalize_css_value(val)
```

- [ ] **Step 3: Verify per-side overrides priority**

Write tests in `tests/test_processors/test_borders.py`:

```python
def test_per_side_override(self) -> None:
    """Per-side options override the margin shorthand."""
    tm = BordersProcessor._build_target_map({
        "margin": 5, "margin_top": 10
    })
    assert tm["margin"] == "5px"
    assert tm["margin-top"] == "10px"
    assert tm["margin-left"] == "5px"  # shorthand still applies to other sides

def test_per_side_alone(self) -> None:
    """Per-side option alone only sets that property."""
    tm = BordersProcessor._build_target_map({"padding_left": 8})
    assert tm["padding-left"] == "8px"
    assert "padding-right" not in tm
    assert "padding" not in tm
```

Run: `pytest tests/test_processors/test_borders.py -v --no-cov`
Expected: all new tests PASS

---

### Task 2: CLI — 10 new options

**Files:**
- Modify: `src/boozarr/cli.py` (add decorators, params, config keys, normalise defaults)
- Modify: `README.md` (options table)

- [ ] **Step 1: Add Click options**

Insert after the existing `--padding` option block:

```python
@click.option(
    "--margin-top", type=int, default=None, is_flag=False, flag_value=2,
    metavar="<int>", help="Target margin-top, px (no value = 2)."
)
@click.option(
    "--margin-bottom", type=int, default=None, is_flag=False, flag_value=2,
    metavar="<int>", help="Target margin-bottom, px (no value = 2)."
)
@click.option(
    "--margin-left", type=int, default=None, is_flag=False, flag_value=2,
    metavar="<int>", help="Target margin-left, px (no value = 2)."
)
@click.option(
    "--margin-right", type=int, default=None, is_flag=False, flag_value=2,
    metavar="<int>", help="Target margin-right, px (no value = 2)."
)
@click.option(
    "--padding-top", type=int, default=None, is_flag=False, flag_value=2,
    metavar="<int>", help="Target padding-top, px (no value = 2)."
)
@click.option(
    "--padding-bottom", type=int, default=None, is_flag=False, flag_value=2,
    metavar="<int>", help="Target padding-bottom, px (no value = 2)."
)
@click.option(
    "--padding-left", type=int, default=None, is_flag=False, flag_value=2,
    metavar="<int>", help="Target padding-left, px (no value = 2)."
)
@click.option(
    "--padding-right", type=int, default=None, is_flag=False, flag_value=2,
    metavar="<int>", help="Target padding-right, px (no value = 2)."
)
```

- [ ] **Step 2: Add params to `cli()`**

```python
    margin_top: int | None,
    margin_bottom: int | None,
    margin_left: int | None,
    margin_right: int | None,
    padding_top: int | None,
    padding_bottom: int | None,
    padding_left: int | None,
    padding_right: int | None,
```

- [ ] **Step 3: Add to config dict**

```python
    config = {
        ...
        "margin_top": margin_top,
        "margin_bottom": margin_bottom,
        "margin_left": margin_left,
        "margin_right": margin_right,
        "padding_top": padding_top,
        "padding_bottom": padding_bottom,
        "padding_left": padding_left,
        "padding_right": padding_right,
    }
```

- [ ] **Step 4: Add to `--normalise` defaults**

```python
    if margin_top is None:
        margin_top = 2
    if margin_bottom is None:
        margin_bottom = 2
    if margin_left is None:
        margin_left = 2
    if margin_right is None:
        margin_right = 2
    if padding_top is None:
        padding_top = 2
    if padding_bottom is None:
        padding_bottom = 2
    if padding_left is None:
        padding_left = 2
    if padding_right is None:
        padding_right = 2
```

- [ ] **Step 5: Update README**

Add 8 rows to the options table after the `--padding` row:

```
| `--margin-top` | — | Target margin-top, px (only when specified) |
| `--margin-bottom` | — | Target margin-bottom, px (only when specified) |
| `--margin-left` | — | Target margin-left, px (only when specified) |
| `--margin-right` | — | Target margin-right, px (only when specified) |
| `--padding-top` | — | Target padding-top, px (only when specified) |
| `--padding-bottom` | — | Target padding-bottom, px (only when specified) |
| `--padding-left` | — | Target padding-left, px (only when specified) |
| `--padding-right` | — | Target padding-right, px (only when specified) |
```

- [ ] **Step 6: Verify**

Run: `boozarr --help | grep -E "margin-|padding-"`
Expected: 8 new options listed

Run: `pytest --no-cov -q`
Expected: all tests pass
