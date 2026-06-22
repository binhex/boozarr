# `--text-indent` CLI Option Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--text-indent` CLI option that controls paragraph first-line indentation, auto-activates only when specified.

**Architecture:** Follows the existing `flag_value` pattern. Added to `CssNormaliseProcessor` via `_PARAGRAPH_PROPS` and `_build_target_map`. Uses `normalize_css_value` for int-to-px conversion.

**Tech Stack:** Python 3.12, Click, pytest

---

### Task 1: CssNormaliseProcessor — text-indent support

**Files:**
- Modify: `src/boozarr/processors/css_normalise.py:14,161-163`

- [ ] **Step 1: Add to `_PARAGRAPH_PROPS`**

```python
_PARAGRAPH_PROPS = ["font-size", "line-height", "text-align", "text-indent"]
```

- [ ] **Step 2: Add to `_build_target_map`**

```python
indent_val = config.get("text_indent")
if indent_val is not None:
    target_map["text-indent"] = normalize_css_value(indent_val)
```

- [ ] **Step 3: Run tests to verify**

Run: `pytest tests/test_processors/test_css_normalise.py -v --no-cov`
Expected: all pass

---

### Task 2: CLI — `--text-indent` option

**Files:**
- Modify: `src/boozarr/cli.py` (add decorator, param, config key, normalise default)

- [ ] **Step 1: Add Click option**

```python
@click.option(
    "--text-indent", type=int, default=None, is_flag=False, flag_value=0,
    metavar="<int>", help="Target text indent, px (no value = 0)."
)
```

- [ ] **Step 2: Add parameter to `cli()`**

```python
text_indent: int | None,
```

- [ ] **Step 3: Add to config dict**

```python
"text_indent": text_indent,
```

- [ ] **Step 4: Add to `--normalise` defaults**

```python
defaults = {
    ...
    "text_indent": 0,
}

if text_indent is None:
    text_indent = defaults["text_indent"]
```

- [ ] **Step 5: Verify CLI and full suite**

Run: `boozarr --help | grep text-indent`
Expected: `--text-indent <int> Target text indent, px (no value = 0).`

Run: `pytest --no-cov -q`
Expected: 134 passed
