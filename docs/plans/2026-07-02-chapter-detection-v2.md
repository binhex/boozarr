# Chapter Detection v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three gaps in chapters processor — false-negative check() when NCX has only placeholder navPoints, `.html` content files not scanned, and no explicit pattern for bare number/Roman numeral chapter headings.

**Architecture:** All changes confined to `chapters.py` (add 1 static method, modify 2 existing methods, append 1 pattern) and `test_chapters.py` (add 6 tests). No new files, no signature changes to public API.

**Tech Stack:** Python 3.12+, pytest, xml.etree.ElementTree, re

---

### Task 1: Smarter `check()` — filter placeholder navPoints

**Files:**
- Modify: `src/boozarr/processors/chapters.py:92-112` (add `_has_real_chapters`, modify `check()`)
- Modify: `tests/test_processors/test_chapters.py` (add test methods)

- [ ] **Step 1: Add `_has_real_chapters` static method to chapters.py**

Insert this method right after `_no_chapters_issue` (after line 117) and before `_label_from_filename`:

```python
@staticmethod
def _has_real_chapters(ncx_root: Any) -> bool:
    """Return True if the NCX has at least one navPoint that is not a
    placeholder pointing to a non-content file (cover, titlepage, etc.)."""
    import xml.etree.ElementTree as ET  # noqa: F811 — already imported at module level
    for np in ncx_root.findall(f".//{{{_NCX_NS}}}navPoint"):
        content = np.find(f"{{{_NCX_NS}}}content")
        if content is not None:
            src: str | None = content.get("src")
            if src:
                from pathlib import Path

                stem = Path(src).stem.lower()
                if not _should_skip_content_file(stem):
                    return True
    return False
```

Note: `ElementTree` and `Path` are already imported at module level. Remove the inline `import` lines — use the existing module-level imports.

Actual code to insert between `_no_chapters_issue` and `_label_from_filename` (after line 117):

```python
    @staticmethod
    def _has_real_chapters(ncx_root: Any) -> bool:
        """Return True if the NCX has at least one navPoint not pointing to a
        known non-content file (cover, title, toc, nav, copyright, about)."""
        for np in ncx_root.findall(f".//{{{_NCX_NS}}}navPoint"):
            content = np.find(f"{{{_NCX_NS}}}content")
            if content is not None:
                src: str | None = content.get("src")
                if src:
                    stem = Path(src).stem.lower()
                    if not _should_skip_content_file(stem):
                        return True
        return False
```

- [ ] **Step 2: Modify `check()` to use `_has_real_chapters`**

Change line 108 in `check()` from:

```python
            if root.findall(f".//{{{_NCX_NS}}}navPoint"):
```

to:

```python
            if self._has_real_chapters(root):
```

- [ ] **Step 3: Write failing tests for `_has_real_chapters`**

Add to `tests/test_processors/test_chapters.py` at the end of the file (before the last line):

```python
class TestHasRealChapters:
    """Tests for _has_real_chapters static method."""

    _NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"

    def test_empty_ncx_returns_false(self) -> None:
        """NCX with no navPoints at all."""
        ncx = f'<ncx xmlns="{self._NCX_NS}"><navMap></navMap></ncx>'
        from xml.etree import ElementTree

        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is False

    def test_placeholder_only_returns_false(self) -> None:
        """Single navPoint pointing to titlepage.xhtml."""
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="s" playOrder="1">'
            "<navLabel><text>Start</text></navLabel>"
            '<content src="titlepage.xhtml"/>'
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree

        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is False

    def test_real_chapter_returns_true(self) -> None:
        """navPoint pointing to a real chapter file."""
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="c1" playOrder="1">'
            "<navLabel><text>Chapter One</text></navLabel>"
            '<content src="chapter1.xhtml"/>'
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree

        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is True

    def test_placeholder_plus_real_returns_true(self) -> None:
        """Mix — placeholder and real chapter."""
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="cover" playOrder="1">'
            "<navLabel><text>Cover</text></navLabel>"
            '<content src="titlepage.xhtml"/>'
            "</navPoint>"
            '<navPoint id="ch1" playOrder="2">'
            "<navLabel><text>The Story</text></navLabel>"
            '<content src="index_split_001.html"/>'
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree

        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is True

    def test_navpoint_without_content_returns_false(self) -> None:
        """navPoint with no <content> child — skip it."""
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="broken" playOrder="1">'
            "<navLabel><text>X</text></navLabel>"
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree

        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is False

    def test_navpoint_without_src_returns_false(self) -> None:
        """navPoint with <content> but no src attribute."""
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="x" playOrder="1">'
            "<navLabel><text>X</text></navLabel>"
            "<content/>"
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree

        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is False
```

- [ ] **Step 4: Write failing integration test for check() with placeholder NCX**

Add this test method to the `TestChaptersCheck` class:

```python
def test_issue_when_ncx_has_only_placeholder_navpoint(self) -> None:
    """NCX with one navPoint pointing to titlepage — should report issue."""
    ncx_with_placeholder = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="x"/></head>
  <navMap>
    <navPoint id="start" playOrder="1"><navLabel><text>Start</text></navLabel><content src="titlepage.xhtml"/></navPoint>
  </navMap>
</ncx>"""
    epub = MagicMock()
    epub.read_file.side_effect = lambda p: {ncx_with_placeholder: ncx_with_placeholder, "content.opf": "<package/>"}[
        p
    ]
    epub.get_opf_path.return_value = "content.opf"
    issues = ChaptersProcessor().check(epub)
    assert len(issues) == 1
    assert issues[0].processor == "chapters"
```

Wait — the `side_effect` dict key is wrong in the above. The first `read_file` call is for "toc.ncx", then "content.opf". Let me fix:

```python
def test_issue_when_ncx_has_only_placeholder_navpoint(self) -> None:
    """NCX with one navPoint pointing to titlepage — should report issue."""
    ncx_with_placeholder = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="x"/></head>
  <navMap>
    <navPoint id="start" playOrder="1"><navLabel><text>Start</text></navLabel><content src="titlepage.xhtml"/></navPoint>
  </navMap>
</ncx>"""
    epub = MagicMock()
    epub.read_file.side_effect = lambda p: {"toc.ncx": ncx_with_placeholder, "content.opf": "<package/>"}[p]
    epub.get_opf_path.return_value = "content.opf"
    issues = ChaptersProcessor().check(epub)
    assert len(issues) == 1
    assert issues[0].processor == "chapters"
```

- [ ] **Step 5: Run all chapter tests — verify failures then passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py -v
```

Expected: 2 test failures (`test_issue_when_ncx_has_only_placeholder_navpoint` and `test_empty_ncx_returns_false` should pass after code is implemented; before implementation `test_issue_when_ncx_has_only_placeholder_navpoint` should FAIL because check() currently passes with any navPoint).

Wait — let me reason about which tests pass/fail before implementation:

- `test_no_issues_when_toc_populated`: The sample NCX has navPoint src="ch1.xhtml" — `_has_real_chapters` returns True → check() returns [] → PASS
- `test_issue_when_toc_empty`: NCX has empty `<navMap/>` — no navPoints → `_has_real_chapters` returns False → check() returns Issue → PASS  
- `test_issue_when_ncx_has_only_placeholder_navpoint`: NEW — NCX has Start→titlepage — `_has_real_chapters` returns False → check() returns Issue → PASS
- `TestHasRealChapters` tests: All should pass since they test the new method directly

All existing tests should still pass since the behavior for populated and empty NCXs is unchanged.

- [ ] **Step 6: Commit**

```bash
cd /data/boozarr
git add src/boozarr/processors/chapters.py tests/test_processors/test_chapters.py
git commit -m "feat: smarter check() filters placeholder navPoints in chapters processor"
```

---

### Task 2: Scan `.html` files in addition to `.xhtml`

**Files:**
- Modify: `src/boozarr/processors/chapters.py:251` (the `rglob` call)
- Modify: `tests/test_processors/test_chapters.py` (add test)

- [ ] **Step 1: Change glob in `_discover_chapters`**

In `_discover_chapters`, line 251, change:

```python
        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
```

to:

```python
        for xhtml_file in sorted(extract_dir.rglob("*.[xh]tml")):
```

Also update the docstring on line 243: change "Scan XHTML files" to "Scan XHTML/HTML files".

- [ ] **Step 2: Write test for `.html` file scanning**

Add to the `TestDiscoverChaptersMultiMatch` class:

```python
def test_finds_chapters_in_html_files(self, tmp_path: Path) -> None:
    """Content in .html files should be scanned."""
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    html_file = extract_dir / "chapter1.html"  # .html NOT .xhtml
    html_file.write_text("<html><body><p>Chapter 1</p></body></html>")
    discovered = ChaptersProcessor._discover_chapters(extract_dir)
    assert len(discovered) == 1
    assert discovered[0][1] == "Chapter 1"
```

- [ ] **Step 3: Write test for mixed `.html` / `.xhtml`**

Add to `TestDiscoverChaptersMultiMatch`:

```python
def test_scans_both_html_and_xhtml(self, tmp_path: Path) -> None:
    """Mixed .html and .xhtml extensions — both scanned."""
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    (extract_dir / "ch1.html").write_text("<html><body><p>Chapter 1</p></body></html>")
    (extract_dir / "ch2.xhtml").write_text("<html><body><p>Chapter 2</p></body></html>")
    discovered = ChaptersProcessor._discover_chapters(extract_dir)
    labels = {m[1] for m in discovered}
    assert "Chapter 1" in labels
    assert "Chapter 2" in labels
```

- [ ] **Step 4: Run tests**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd /data/boozarr
git add src/boozarr/processors/chapters.py tests/test_processors/test_chapters.py
git commit -m "feat: scan .html files alongside .xhtml in chapters processor"
```

---

### Task 3: Add heading-number pattern (digits + Roman numerals)

**Files:**
- Modify: `src/boozarr/processors/chapters.py:12-17` (append to `_CHAPTER_PATTERNS`)
- Modify: `tests/test_processors/test_chapters.py` (add tests)

- [ ] **Step 1: Append new pattern to `_CHAPTER_PATTERNS`**

After the existing four patterns (line 17), add:

```python
    re.compile(r"<h[1-6][^>]*>\s*(\d+|[IVXLCDM]+)\s*</h[1-6]>", re.IGNORECASE),
```

The full list becomes:

```python
_CHAPTER_PATTERNS = [
    re.compile(r"Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"Part\s+\d+", re.IGNORECASE),
    re.compile(r"Section\s+\d+", re.IGNORECASE),
    re.compile(r"CHAPTER\s+\w+", re.IGNORECASE),
    re.compile(r"<h[1-6][^>]*>\s*(\d+|[IVXLCDM]+)\s*</h[1-6]>", re.IGNORECASE),
]
```

- [ ] **Step 2: Write test — Roman numeral in h2 is detected**

Add to `TestDiscoverChaptersMultiMatch`:

```python
def test_detects_roman_numeral_in_h2(self, tmp_path: Path) -> None:
    """<h2>IV</h2> should be detected by the heading-number pattern."""
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    xhtml = extract_dir / "chapter.xhtml"
    xhtml.write_text("<html><body><h2>IV</h2><p>Text</p></body></html>")
    discovered = ChaptersProcessor._discover_chapters(extract_dir)
    assert len(discovered) == 2  # pattern match + h1/h2 fallback also fires
```

Wait — there's a subtlety. The new pattern matches the full heading tag content via `finditer()` on `content`. So `match.group(0)` for `<h2>IV</h2>` would be... let me think.

The pattern is `r"<h[1-6][^>]*>\s*(\d+|[IVXLCDM]+)\s*</h[1-6]>"` and `finditer()` is called on the full HTML content string. So `match.group(0)` would be the full match string: `<h2>IV</h2>`.

But wait — the pattern has a capture group `(\d+|[IVXLCDM]+)`. With `finditer()`, `match.group(0)` returns the full match. The full match is `<h2>IV</h2>` (or similar). That's the label that gets stored.

Then the `matched` flag is set to `True`, so the h1/h2 fallback doesn't fire. The check for `not matched` — the h1/h2 fallback only fires when no pattern matched at all. Since the new pattern DID match, `matched = True`, and the fallback is skipped.

Wait, but the fallback pattern `<h[12][^>]*>(.+?)</h[12]>` would match the same content. But since `matched = True` after the new pattern match, the fallback is skipped. So only 1 entry per heading, not 2.

But hmm, let me reconsider. The label stored is `match.group(0)` which is the full HTML tag: `<h2 class="calibre2" id="calibre_pb_0">IV</h2>`. That's ugly.

Looking at the existing code more carefully:

```python
for pattern in _CHAPTER_PATTERNS:
    for match in pattern.finditer(content):
        pos = match.start()
        if (rel_path, pos) not in seen:
            discovered.append((rel_path, match.group(0)))
            seen.add((rel_path, pos))
        matched = True
```

For patterns like `Chapter\s+\d+`, `match.group(0)` returns just "Chapter 1" — clean text. But for the new pattern `<h[1-6][^>]*>\s*(\d+|[IVXLCDM]+)\s*</h[1-6]>`, `match.group(0)` returns the full tag like `<h2>IV</h2>`.

This is a problem. The label in the NCX would be `<h2>IV</h2>` instead of just "IV".

I need to fix this. The pattern needs to have the heading text as group 1, and we need to use `match.group(1)` instead of `match.group(0)` for this pattern.

But the current code always uses `match.group(0)`. There are a few options:
1. Change the discovery loop to try `match.group(1)` first, fall back to `match.group(0)`
2. Use a non-capturing group for the heading tag parts so group(0) is just the number
3. Strip HTML tags from the label after matching

Option 2 is cleanest. Use lookbehind and lookahead (but lookbehind in Python requires fixed-width, and the tag attributes vary). 

Option 1 is simplest:

```python
label = match.group(1) or match.group(0)
```

Or:
```python
label = match.group(1) if match.lastindex else match.group(0)
```

Or use named groups:
```python
re.compile(r"<h[1-6][^>]*>\s*(?P<label>\d+|[IVXLCDM]+)\s*</h[1-6]>", re.IGNORECASE)
```

Then:
```python
label = match.group("label") if "label" in match.groupdict() else match.group(0)
```

Actually the simplest approach: 

```python
label = match.group(1) if match.lastindex else match.group(0)
```

Where `match.lastindex` is the index of the last capturing group, or `None` if no groups.

Let me update the plan to handle this. The plan should:
1. Append the pattern with a named capture group `(?P<label>...)`
2. Modify the discovery loop to use `match.group("label")` when available, otherwise `match.group(0)`

Actually, looking at this more carefully, I think the cleanest approach for a plan is:
- Change the append line in the loop from `discovered.append((rel_path, match.group(0)))` to extract the label properly

OK let me revise the plan to account for this. I'll use a named group approach. Let me update the plan.

Wait, actually, let me think about this differently. The simplest fix that doesn't change the loop for ALL patterns is to just NOT include the HTML tags in the match group(0). But that's not possible with regex alone without lookbehind/lookahead (which Python supports but with complexity).

Alternatively, I can modify the capture and store logic just slightly:

```python
label = match.group(1) if match.lastindex else match.group(0)
discovered.append((rel_path, label))
```

This works for all patterns because:
- `Chapter\s+\d+` has no capturing groups → `match.lastindex` is `None` → uses `match.group(0)` → "Chapter 1"
- `<h[1-6][^>]*>\s*(\d+|[IVXLCDM]+)\s*</h[1-6]>` has one capturing group → `match.lastindex` is 1 → uses `match.group(1)` → "IV"

This is clean and handles all cases. Let me update the plan.

Actually, I should note that this changes the existing patterns' behavior too. But since existing patterns have no capturing groups, `match.lastindex` is `None`, so `match.group(0)` is used — same as before. No behavior change for existing patterns.

Let me rewrite the plan now, being careful about this detail.<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="write">
<｜｜DSML｜｜parameter name="content" string="true"># Chapter Detection v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three gaps in chapters processor — false-negative `check()` when NCX has only placeholder navPoints, `.html` content files not scanned, and no explicit pattern for bare number / Roman numeral chapter headings in `<h1>`–`<h6>` tags.

**Architecture:** All changes confined to `chapters.py` (add 1 static method, modify `check()`, modify `_discover_chapters` glob + label extraction, append 1 pattern) and `test_chapters.py` (add ~8 test methods). No new files, no signature changes to public API.

**Tech Stack:** Python 3.12+, pytest, xml.etree.ElementTree, re

**Before starting:** Read the spec at `docs/specs/2026-07-02-chapter-detection-v2-design.md`.

---

### Task 1: Smarter `check()` — filter placeholder navPoints

**Files:**
- Modify: `src/boozarr/processors/chapters.py:108` (change the `findall` call)
- Insert: `src/boozarr/processors/chapters.py` after line 117 (add `_has_real_chapters`)
- Modify: `tests/test_processors/test_chapters.py` (add test class + 1 integration test)

- [ ] **Step 1: Add `_has_real_chapters` static method**

Insert after `_no_chapters_issue` (after the docstring `fix_possible=True` line, ~line 117):

```python
    @staticmethod
    def _has_real_chapters(ncx_root: Any) -> bool:
        """Return True if the NCX has at least one navPoint not pointing to a
        known non-content file (cover, title, toc, nav, copyright, about)."""
        for np in ncx_root.findall(f".//{{{_NCX_NS}}}navPoint"):
            content = np.find(f"{{{_NCX_NS}}}content")
            if content is not None:
                src: str | None = content.get("src")
                if src:
                    stem = Path(src).stem.lower()
                    if not _should_skip_content_file(stem):
                        return True
        return False
```

`_NCX_NS`, `Path`, and `_should_skip_content_file` are already defined at module level — no new imports needed.

- [ ] **Step 2: Modify `check()` to use `_has_real_chapters`**

In `check()`, line 108, change:

```python
            if root.findall(f".//{{{_NCX_NS}}}navPoint"):
```

to:

```python
            if self._has_real_chapters(root):
```

- [ ] **Step 3: Write unit tests for `_has_real_chapters`**

Add this class at the end of `tests/test_processors/test_chapters.py`:

```python
class TestHasRealChapters:
    """Tests for _has_real_chapters static method."""

    _NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"

    def test_empty_ncx_returns_false(self) -> None:
        ncx = f'<ncx xmlns="{self._NCX_NS}"><navMap></navMap></ncx>'
        from xml.etree import ElementTree
        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is False

    def test_placeholder_only_returns_false(self) -> None:
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="s" playOrder="1">'
            "<navLabel><text>Start</text></navLabel>"
            '<content src="titlepage.xhtml"/>'
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree
        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is False

    def test_real_chapter_returns_true(self) -> None:
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="c1" playOrder="1">'
            "<navLabel><text>Chapter One</text></navLabel>"
            '<content src="chapter1.xhtml"/>'
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree
        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is True

    def test_placeholder_plus_real_returns_true(self) -> None:
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="cover" playOrder="1">'
            "<navLabel><text>Cover</text></navLabel>"
            '<content src="titlepage.xhtml"/>'
            "</navPoint>"
            '<navPoint id="ch1" playOrder="2">'
            "<navLabel><text>The Story</text></navLabel>"
            '<content src="index_split_001.html"/>'
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree
        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is True

    def test_navpoint_without_content_returns_false(self) -> None:
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="broken" playOrder="1">'
            "<navLabel><text>X</text></navLabel>"
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree
        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is False

    def test_navpoint_without_src_returns_false(self) -> None:
        ncx = (
            f'<ncx xmlns="{self._NCX_NS}"><navMap>'
            '<navPoint id="x" playOrder="1">'
            "<navLabel><text>X</text></navLabel>"
            "<content/>"
            "</navPoint>"
            "</navMap></ncx>"
        )
        from xml.etree import ElementTree
        root = ElementTree.fromstring(ncx)
        assert ChaptersProcessor._has_real_chapters(root) is False
```

- [ ] **Step 4: Write integration test for check() with placeholder NCX**

Add to the `TestChaptersCheck` class:

```python
    def test_issue_when_ncx_has_only_placeholder_navpoint(self) -> None:
        """NCX with one navPoint pointing to titlepage — should report issue."""
        ncx_with_placeholder = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="x"/></head>
  <navMap>
    <navPoint id="start" playOrder="1"><navLabel><text>Start</text></navLabel><content src="titlepage.xhtml"/></navPoint>
  </navMap>
</ncx>"""
        epub = MagicMock()
        epub.read_file.side_effect = lambda p: {"toc.ncx": ncx_with_placeholder, "content.opf": "<package/>"}[p]
        epub.get_opf_path.return_value = "content.opf"
        issues = ChaptersProcessor().check(epub)
        assert len(issues) == 1
        assert issues[0].processor == "chapters"
        assert issues[0].fix_possible is True
```

- [ ] **Step 5: Run tests**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py -v
```

Before implementation, `test_issue_when_ncx_has_only_placeholder_navpoint` should FAIL (check() currently passes with any navPoint). All other existing tests should still pass. After implementation, all pass.

- [ ] **Step 6: Commit**

```bash
cd /data/boozarr
git add src/boozarr/processors/chapters.py tests/test_processors/test_chapters.py
git commit -m "feat: smarter check() filters placeholder navPoints in chapters processor"
```

---

### Task 2: Scan `.html` files in addition to `.xhtml`

**Files:**
- Modify: `src/boozarr/processors/chapters.py:251` (the `rglob` call)
- Modify: `tests/test_processors/test_chapters.py` (add 2 test methods)

- [ ] **Step 1: Change glob in `_discover_chapters`**

In `_discover_chapters`, line ~251, change:

```python
        for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
```

to:

```python
        for xhtml_file in sorted(extract_dir.rglob("*.[xh]tml")):
```

Also update the docstring on line ~243: `"Scan XHTML files"` → `"Scan XHTML/HTML files"`.

- [ ] **Step 2: Write test for `.html` file scanning**

Add to `TestDiscoverChaptersMultiMatch`:

```python
    def test_finds_chapters_in_html_files(self, tmp_path: Path) -> None:
        """Content in .html files should be discovered."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        html_file = extract_dir / "chapter1.html"
        html_file.write_text("<html><body><p>Chapter 1</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        assert len(discovered) == 1
        assert discovered[0][1] == "Chapter 1"
```

- [ ] **Step 3: Write test for mixed `.html` / `.xhtml`**

```python
    def test_scans_both_html_and_xhtml(self, tmp_path: Path) -> None:
        """Mixed .html and .xhtml extensions — both should be scanned."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        (extract_dir / "ch1.html").write_text("<html><body><p>Chapter 1</p></body></html>")
        (extract_dir / "ch2.xhtml").write_text("<html><body><p>Chapter 2</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        labels = {m[1] for m in discovered}
        assert "Chapter 1" in labels
        assert "Chapter 2" in labels
```

- [ ] **Step 4: Run tests**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd /data/boozarr
git add src/boozarr/processors/chapters.py tests/test_processors/test_chapters.py
git commit -m "feat: scan .html files alongside .xhtml in chapters processor"
```

---

### Task 3: Add heading-number pattern + capture-group label extraction

**Files:**
- Modify: `src/boozarr/processors/chapters.py:12-17` (append to `_CHAPTER_PATTERNS`)
- Modify: `src/boozarr/processors/chapters.py:277` (change `match.group(0)` → group-aware label)
- Modify: `tests/test_processors/test_chapters.py` (add 4 test methods)

**Important detail:** The new pattern uses a capturing group to extract just the heading text. But `_scan_file_for_chapters` currently uses `match.group(0)` for ALL patterns (which returns the full match). For patterns without groups (like `Chapter\s+\d+`), `group(0)` is correct. For the new pattern, `group(0)` would return the full `<h2>IV</h2>` tag — we need just "IV".

**Fix:** Change the label extraction to use `match.group(1)` when capturing groups exist, otherwise `match.group(0)`. This is backward-compatible — existing patterns have no groups, so `group(0)` is still used.

- [ ] **Step 1: Append new pattern to `_CHAPTER_PATTERNS`**

After line 17 (the `CHAPTER\s+\w+` pattern), add:

```python
    re.compile(r"<h[1-6][^>]*>\s*(\d+|[IVXLCDM]+)\s*</h[1-6]>", re.IGNORECASE),
```

The full list becomes (5 patterns):

```python
_CHAPTER_PATTERNS = [
    re.compile(r"Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"Part\s+\d+", re.IGNORECASE),
    re.compile(r"Section\s+\d+", re.IGNORECASE),
    re.compile(r"CHAPTER\s+\w+", re.IGNORECASE),
    re.compile(r"<h[1-6][^>]*>\s*(\d+|[IVXLCDM]+)\s*</h[1-6]>", re.IGNORECASE),
]
```

- [ ] **Step 2: Modify label extraction to use capture group when available**

In `_scan_file_for_chapters`, line ~277, change:

```python
                    discovered.append((rel_path, match.group(0)))
```

to:

```python
                    label = match.group(1) if match.lastindex else match.group(0)
                    discovered.append((rel_path, label))
```

This way:
- Existing patterns (no groups) → `match.lastindex` is `None` → uses `match.group(0)` (unchanged behavior)
- New pattern (has group 1) → `match.lastindex` is `1` → uses `match.group(1)` = `"IV"` or `"3"`

- [ ] **Step 3: Write test — Roman numeral in h2**

Add to `TestDiscoverChaptersMultiMatch`:

```python
    def test_detects_roman_numeral_in_h2(self, tmp_path: Path) -> None:
        """<h2>IV</h2> — detected by heading-number pattern, label is 'IV'."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapter.xhtml"
        xhtml.write_text("<html><body><h2 class=\"calibre2\" id=\"pb_0\">IV</h2><p>Text</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        assert len(discovered) == 1
        assert discovered[0][1] == "IV"
```

- [ ] **Step 4: Write test — plain number in h1**

```python
    def test_detects_number_in_h1(self, tmp_path: Path) -> None:
        """<h1>3</h1> — detected, label is '3'."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapter.xhtml"
        xhtml.write_text("<html><body><h1>3</h1><p>Text</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        assert len(discovered) == 1
        assert discovered[0][1] == "3"
```

- [ ] **Step 5: Write test — non-number heading falls through to h1/h2 fallback**

```python
    def test_non_number_heading_uses_fallback(self, tmp_path: Path) -> None:
        """<h2>Introduction</h2> — NOT matched by heading-number pattern,
        but caught by h1/h2 fallback."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapter.xhtml"
        xhtml.write_text("<html><body><h2>Introduction</h2><p>Text</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        assert len(discovered) == 1
        assert discovered[0][1] == "Introduction"
```

- [ ] **Step 6: Write test — complex heading NOT matched by heading-number pattern**

```python
    def test_complex_heading_not_matched_by_number_pattern(self, tmp_path: Path) -> None:
        """<h2>Henry VIII Edition</h2> — contains Roman numeral but also other
        text, so heading-number pattern does NOT match. Fallback catches it."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapter.xhtml"
        xhtml.write_text("<html><body><h2>Henry VIII Edition</h2><p>Text</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        assert len(discovered) == 1
        assert discovered[0][1] == "Henry VIII Edition"
```

- [ ] **Step 7: Write test — heading with whitespace only**

```python
    def test_heading_number_with_whitespace(self, tmp_path: Path) -> None:
        """<h2> XIV </h2> — whitespace around numeral, matched."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapter.xhtml"
        xhtml.write_text("<html><body><h2> XIV </h2><p>Text</p></body></html>")
        discovered = ChaptersProcessor._discover_chapters(extract_dir)
        assert len(discovered) == 1
        assert discovered[0][1] == "XIV"
```

- [ ] **Step 8: Run tests**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py -v
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
cd /data/boozarr
git add src/boozarr/processors/chapters.py tests/test_processors/test_chapters.py
git commit -m "feat: add heading-number pattern for bare Roman/digit chapter headings"
```

---

### Task 4: End-to-end integration test with real EPUB scenario

**Files:**
- Modify: `tests/test_processors/test_chapters.py` (add 1 integration test)

- [ ] **Step 1: Write test — placeholder NCX with .html content files and Roman numeral headings**

Add to `TestChaptersProcessorIntegration`:

```python
    def test_end_to_end_placeholder_ncx_with_html_roman_headings(self, tmp_path: Path) -> None:
        """Simulates the '1408' EPUB scenario:
        - NCX has one placeholder navPoint (Start → titlepage)
        - Content files use .html extension
        - Chapters marked with <h2> Roman numerals (I, II, III)
        verify that check() detects the issue and fix() populates NCX.
        """
        epub_path = tmp_path / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" '
                'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="content.opf" '
                'media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "content.opf",
                '<?xml version="1.0"?><package>'
                "<manifest>"
                '<item id="title" href="titlepage.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="ch1" href="index_split_001.html" media-type="application/xhtml+xml"/>'
                '<item id="ch2" href="index_split_002.html" media-type="application/xhtml+xml"/>'
                '<item id="ch3" href="index_split_003.html" media-type="application/xhtml+xml"/>'
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
                "</manifest>"
                "<spine>"
                '<itemref idref="title"/>'
                '<itemref idref="ch1"/>'
                '<itemref idref="ch2"/>'
                '<itemref idref="ch3"/>'
                "</spine></package>",
            )
            zf.writestr(
                "toc.ncx",
                '<?xml version="1.0"?>'
                '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">'
                "<navMap>"
                '<navPoint id="start" playOrder="1">'
                "<navLabel><text>Start</text></navLabel>"
                '<content src="titlepage.xhtml"/>'
                "</navPoint>"
                "</navMap></ncx>",
            )
            zf.writestr("titlepage.xhtml", "<html><body><p>Title</p></body></html>")
            zf.writestr("index_split_001.html", "<html><body><h2 class=\"calibre2\">I</h2><p>Chapter one text.</p></body></html>")
            zf.writestr("index_split_002.html", "<html><body><h2 class=\"calibre2\">II</h2><p>Chapter two text.</p></body></html>")
            zf.writestr("index_split_003.html", "<html><body><h2 class=\"calibre2\">III</h2><p>Chapter three text.</p></body></html>")

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = ChaptersProcessor()

        # Before: check() should report issue (placeholder-only NCX)
        issues = processor.check(wrapper)
        assert len(issues) == 1, f"Expected 1 issue (placeholder-only NCX), got {len(issues)}"

        # Fix should add chapter entries
        fixes = processor.fix(wrapper, issues, {})
        assert len(fixes) == 1

        # Repack and verify
        wrapper.repack(epub_path)
        wrapper2 = EpubWrapper(epub_path)
        issues_after = processor.check(wrapper2)
        assert len(issues_after) == 0, f"After fix, expected 0 issues, got {len(issues_after)}"

        # Verify NCX content
        with zipfile.ZipFile(epub_path, "r") as zf:
            ncx_content = zf.read("toc.ncx").decode()
            assert "I" in ncx_content
            assert "II" in ncx_content
            assert "III" in ncx_content
```

- [ ] **Step 2: Run the integration test**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestChaptersProcessorIntegration::test_end_to_end_placeholder_ncx_with_html_roman_headings -v
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

```bash
cd /data/boozarr && uv run pytest tests/ -v
```

Expected: all 173+ tests pass, including all new chapter tests.

- [ ] **Step 4: Commit**

```bash
cd /data/boozarr
git add tests/test_processors/test_chapters.py
git commit -m "test: end-to-end integration test for placeholder NCX + Roman numeral headings"
```

---

### Final Check

After all tasks complete, run the full quality gate:

```bash
cd /data/boozarr && uv run pytest --cov=boozarr --cov-fail-under=80 -v && uv run ruff check --fix . && uv run ruff format . && uv run mypy .
```

All gates must pass.
