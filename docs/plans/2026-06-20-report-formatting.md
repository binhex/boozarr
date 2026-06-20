# Report Formatting Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the boozarr CLI output to show old→new values in fix details and present the summary as a clean table-style footer.

**Architecture:** Three layers change: (1) processors populate `Fix.old_value`/`new_value` with actual CSS values, (2) pipeline formats fix_details using `"{proc}: {prop} {old} → {new}"`, (3) report renders a table-style summary with divider lines and aligned columns.

**Tech Stack:** Python 3.12+, Click, Loguru, pytest

---

## Files to Modify

| File | What changes |
|------|-------------|
| `src/boozarr/processors/borders.py` | `fix()` — populate `Fix(old_value=..., new_value=...)` from parsed CSS values |
| `src/boozarr/processors/css_normalise.py` | Same as borders |
| `src/boozarr/pipeline.py` | `_run_processors()` — format fix_details string using `fix.old_value`/`new_value` |
| `src/boozarr/report.py` | `final_summary()` — table-style with `─` divider, aligned columns, inline change summaries |
| `tests/test_pipeline.py` | Update `test_dry_run_does_not_count_fixes` and fix-detail assertions |
| `tests/test_report.py` | Update `test_log_line_with_fix_details`, `test_final_summary_with_fix_breakdown` |
| `tests/test_processors/test_borders.py` | Update assertions to include old/new values in Fix objects |

---

### Task 1: Populate Fix.old_value and new_value in BordersProcessor

**Files:**
- Modify: `src/boozarr/processors/borders.py:166-185`

The `fix()` method currently sets `Fix(old_value=i.description, ...)` where `i.description` is the full string `"Non-standard padding: '10px'"`. Change it to parse the old CSS value from the description and pass the target from `target_map` as `new_value`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_processors/test_borders.py` inside `TestBordersProcessorEdgeCases`:

```python
def test_fix_populates_old_and_new_values(self, tmp_path: Path) -> None:
    """Fix objects should contain the old CSS value and the new target value."""
    epub_path = tmp_path / "book.epub"
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", "<container/>")
        zf.writestr("OEBPS/content.opf", "<package/>")
        zf.writestr("OEBPS/styles.css", "body { padding: 10px; }")
        zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Text</p></body></html>")
    wrapper = EpubWrapper(epub_path)
    extract_dir = tmp_path / "extracted"
    wrapper.extract(extract_dir)
    processor = BordersProcessor()
    issues = processor.check(wrapper)
    assert len(issues) >= 1
    fixes = processor.fix(wrapper, issues, {"padding": "1px"})
    assert len(fixes) >= 1
    assert fixes[0].old_value == "10px", f"Expected old_value='10px', got {fixes[0].old_value!r}"
    assert fixes[0].new_value == "1px", f"Expected new_value='1px', got {fixes[0].new_value!r}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_processors/test_borders.py::TestBordersProcessorEdgeCases::test_fix_populates_old_and_new_values -v --tb=short`
Expected: FAIL — `old_value` is `"Non-standard padding: '10px'"` not `"10px"`

- [ ] **Step 3: Implement the fix**

In `src/boozarr/processors/borders.py`, change the `fix()` return statement to extract the old CSS value from `i.description`:

```python
        # Parse old CSS value from issue description: "Non-standard padding: '10px'" → "10px"
        import re
        _OLD_VALUE_RE = re.compile(r"'([^']+)'")

        return [
            Fix(
                processor=self.name,
                location=i.location,
                description=f"Normalised {i.location}",
                old_value=(m.group(1) if (m := _OLD_VALUE_RE.search(i.description)) else i.description),
                new_value=target_map.get(i.location.split()[-1].strip("()"), ""),
            )
            for i in issues
            if i.location.split()[-1].strip("()") in target_map
        ]
```

Move the `import re` and `_OLD_VALUE_RE` to the top of the file near the other regex constants.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_processors/test_borders.py::TestBordersProcessorEdgeCases::test_fix_populates_old_and_new_values -v --tb=short`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/processors/borders.py tests/test_processors/test_borders.py
git commit -m "feat: populate Fix old/new values in BordersProcessor"
```

---

### Task 2: Populate Fix.old_value and new_value in CssNormaliseProcessor

**Files:**
- Modify: `src/boozarr/processors/css_normalise.py:131-148`

Same pattern as Task 1. The `check()` issues have the same description format `"Non-standard font-size: '2em'"`.

- [ ] **Step 1: Add test for old/new values**

Add to `tests/test_processors/test_css_normalise.py` inside `TestCssNormaliseEdgeCases`:

```python
def test_fix_populates_old_and_new_values(self, tmp_path: Path) -> None:
    """Fix objects should contain the old CSS value and the new target value."""
    epub_path = tmp_path / "book.epub"
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", "<container/>")
        zf.writestr("OEBPS/content.opf", "<package/>")
        zf.writestr("OEBPS/styles.css", "body { font-size: 3em; }")
        zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Text</p></body></html>")
    wrapper = EpubWrapper(epub_path)
    extract_dir = tmp_path / "extracted"
    wrapper.extract(extract_dir)
    processor = CssNormaliseProcessor()
    issues = processor.check(wrapper)
    assert len(issues) >= 1
    fixes = processor.fix(wrapper, issues, {"font_size": "1em"})
    assert len(fixes) >= 1
    assert fixes[0].old_value == "3em"
    assert fixes[0].new_value == "1em"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_processors/test_css_normalise.py::TestCssNormaliseEdgeCases::test_fix_populates_old_and_new_values -v --tb=short`
Expected: FAIL — `old_value` is wrong

- [ ] **Step 3: Implement the fix**

In `src/boozarr/processors/css_normalise.py`, add the same regex-based old-value extraction in `fix()`:

```python
        import re
        _OLD_VALUE_RE = re.compile(r"'([^']+)'")

        return [
            Fix(
                processor=self.name,
                location=i.location,
                description=f"Normalised {i.location}",
                old_value=(m.group(1) if (m := _OLD_VALUE_RE.search(i.description)) else i.description),
                new_value=target_map.get(i.location.split()[-1].strip("()"), ""),
            )
            for i in issues
            if i.location.split()[-1].strip("()") in target_map
        ]
```

Move `_OLD_VALUE_RE` to the module-level regex constants (near `_CSS_COMMENT_RE` etc.) and import `re` if not already there.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_processors/test_css_normalise.py::TestCssNormaliseEdgeCases::test_fix_populates_old_and_new_values -v --tb=short`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/processors/css_normalise.py tests/test_processors/test_css_normalise.py
git commit -m "feat: populate Fix old/new values in CssNormaliseProcessor"
```

---

### Task 3: Format fix_details using old/new values in Pipeline

**Files:**
- Modify: `src/boozarr/pipeline.py:162-164`

Currently the fix_details line is `"{proc.name}: {desc}"` where `desc` is `fix.description` (e.g. `"Normalised CSS (padding)"`). Change it to use `fix.old_value` and `fix.new_value`:

Format: `"{proc.name}: {prop_name} {old_value}→{new_value}"` or `"{proc.name}: {prop_name} {old_value}=={new_value}"` when values match.

- [ ] **Step 1: Write failing test**

In `tests/test_pipeline.py`, find the existing fix-detail test. Update its assertion to match the new format. For the dry-run test:

```python
def test_fix_details_show_old_new_values(self, tmp_path: Path) -> None:
    """Fix details should show old → new CSS values."""
    import zipfile
    from boozarr.db import ProcessingDB
    from boozarr.processors.borders import BordersProcessor

    epub_path = tmp_path / "book.epub"
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", "<container/>")
        zf.writestr("OEBPS/content.opf", "<package/>")
        zf.writestr("OEBPS/styles.css", "body { padding: 10px; }")
        zf.writestr("OEBPS/ch1.xhtml", "<p>Text</p>")

    db = ProcessingDB(tmp_path / "test.db")
    pipeline = Pipeline(
        db=db,
        processors=[BordersProcessor()],
        config={"padding": "1px"},
        fix=False,
    )
    result = pipeline.process_epub(epub_path)
    assert len(result["fix_details"]) > 0
    detail = result["fix_details"][0]
    assert "padding" in detail, f"Expected 'padding' in {detail}"
    assert "10px" in detail, f"Expected old value '10px' in {detail}"
    assert "1px" in detail, f"Expected new value '1px' in {detail}"
    assert "→" in detail or "==" in detail, f"Expected arrow in {detail}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -k "test_fix_details_show_old_new_values" -v --tb=short`
Expected: FAIL — fix_details are in old format `"borders: Normalised CSS (padding)"`

- [ ] **Step 3: Implement the fix**

In `src/boozarr/pipeline.py`, change the fix_details formatting inside `_run_processors()`:

```python
                        for fix in fixes:
                            prop_name = fix.location.split()[-1].strip("()")
                            old = fix.old_value or "?"
                            new = fix.new_value or "?"
                            arrow = " → " if old != new else " == "
                            fix_details.append(f"{proc.name}: {prop_name} {old}{arrow}{new}")
```

- [ ] **Step 4: Run tests to verify**

Run: `uv run pytest tests/test_pipeline.py -v --tb=short`
Expected: ALL PASS (including the new and existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/pipeline.py tests/test_pipeline.py
git commit -m "feat: format fix_details with old→new values in pipeline"
```

---

### Task 4: Table-style summary in Report

**Files:**
- Modify: `src/boozarr/report.py:51-71`

Rewrite `final_summary()` to produce the table-style output with divider lines and aligned columns.

- [ ] **Step 1: Write failing test for new format**

In `tests/test_report.py`, update `test_final_summary_counts` and `test_final_summary_with_fix_breakdown` to assert the new format:

```python
def test_final_summary_table_format(self) -> None:
    r = Report()
    r.log_line("a.epub", "ok", issues=0, fixes=3)
    r.log_line("b.epub", "warn", issues=2, fixes=1)
    r.log_line("c.epub", "error", issues=0, fixes=0)
    r.log_line("d.epub", "skip", issues=0, fixes=0)
    s = r.final_summary(duration_s=12.4)
    # Should have divider lines
    assert "─" in s
    # Should show counts
    assert "Files processed:" in s
    assert "1 skipped" in s
    assert "1 errors" in s
    assert "Issues found:" in s
    assert "Fixes applied:" in s
    assert "Duration:" in s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_report.py::TestReport::test_final_summary_table_format -v --tb=short`
Expected: FAIL — format is different

- [ ] **Step 3: Implement the fix**

Replace the `final_summary()` method in `src/boozarr/report.py`:

```python
    def final_summary(self, duration_s: float) -> str:
        """Produce a table-style summary with divider lines and aligned columns."""
        non_skipped = self.total - self.skipped - self.errors
        summary_parts = [
            "─" * 40,
            f"  Files processed:  {self.total}  ({self.skipped} skipped, {self.errors} errors)",
            f"  Issues found:     {self.total_issues}",
            f"  Fixes applied:    {self.total_fixes}",
        ]

        if self._fix_details_list:
            counter: Counter = Counter()
            change_map: dict[str, list[str]] = {}
            for d in self._fix_details_list:
                processor = d.split(":", 1)[0] if ":" in d else "unknown"
                counter[processor] += 1
                # Extract change summary from fix detail (already formatted)
                change_part = d.split(":", 1)[1].strip() if ":" in d else d
                change_map.setdefault(processor, []).append(change_part)

            summary_parts.append("")
            summary_parts.append("  Fixes by processor:")
            for proc in sorted(counter.keys()):
                count = counter[proc]
                changes = ", ".join(change_map.get(proc, []))
                summary_parts.append(f"    {proc:<16} {count:>3}   {changes}")

        summary_parts.append("─" * 40)
        summary_parts.append(f"  Duration: {duration_s:.1f}s")
        return "\n".join(summary_parts)
```

- [ ] **Step 4: Run full test suite to verify**

Run: `uv run pytest -v --tb=short`
Expected: ALL PASS (102/102)

- [ ] **Step 5: Commit**

```bash
git add src/boozarr/report.py tests/test_report.py
git commit -m "feat: table-style summary with divider lines and change details"
```

---

### Task 5: Update existing assertions for new format

**Files:**
- Modify: `tests/test_report.py` — update `test_log_line_with_fix_details` to match new fix_details format
- Modify: `tests/test_pipeline.py` — update `test_dry_run_does_not_count_fixes` if needed

- [ ] **Step 1: Audit all test assertions for format changes**

Check every test that asserts fix_details content, summary format, or Fix object properties. Update them to match the new `"borders: padding 10px → 1px"` format.

Specifically:
- `tests/test_report.py::test_log_line_with_fix_details` — currently checks for `"metadata"` and `"Foundation"` in the line. Update to check the new arrow format.
- `tests/test_report.py::test_final_summary_with_fix_breakdown` — currently checks for `"chapters"`, `"metadata"`, `"borders"` in summary. Update to check for table format.
- `tests/test_pipeline.py` — the existing tests should work if the fix_details format change is backward-compatible. Verify they pass.

- [ ] **Step 2: Run full suite to verify**

Run: `uv run pytest -v --tb=short`
Expected: ALL PASS (102/102)

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: update assertions for new report format"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:** Every requirement from the spec (old→new arrows, table-style summary, divider lines, aligned columns) is covered by a task.
- [ ] **Placeholder scan:** No TBDs, TODOs, or incomplete code snippets in the tasks above.
- [ ] **Type consistency:** `Fix.old_value` and `Fix.new_value` are `str` throughout. The `_OLD_VALUE_RE` regex is defined consistently in both processors.
