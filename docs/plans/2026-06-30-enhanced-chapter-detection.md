# Enhanced Chapter Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `_discover_chapters` to find ALL chapter markers in every XHTML file (not just first), and add a spine-based fallback when no text markers exist.

**Architecture:** Three new `@staticmethod` helpers (`_label_from_filename`, `_resolve_spine_order`, `_discover_from_spine`) are added to `ChaptersProcessor`. The existing `_discover_chapters` is rewritten to use `finditer()` instead of `search()`+`break`, and `fix()` chains the two discovery methods (patterns → spine fallback). No changes to the pipeline, CLI, or any other processor.

**Tech Stack:** Python 3.12+, pytest, `xml.etree.ElementTree`, `re`

---

### Task 1: `_label_from_filename` helper

**Files:**
- Modify: `src/boozarr/processors/chapters.py` (add new method)
- Test: `tests/test_processors/test_chapters.py` (add test class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_processors/test_chapters.py`:

```python
class TestLabelFromFilename:
    """Tests for _label_from_filename helper."""

    def test_extracts_trailing_digits(self) -> None:
        assert ChaptersProcessor._label_from_filename("chapter_3") == "Chapter 3"
        assert ChaptersProcessor._label_from_filename("ch01") == "Chapter 1"
        assert ChaptersProcessor._label_from_filename("part0007") == "Chapter 7"

    def test_strips_leading_zeros(self) -> None:
        assert ChaptersProcessor._label_from_filename("split_005") == "Chapter 5"
        assert ChaptersProcessor._label_from_filename("temp_calibre_txt_input_to_html_split_001") == "Chapter 1"

    def test_mixed_digits_uses_trailing(self) -> None:
        assert ChaptersProcessor._label_from_filename("05_c1") == "Chapter 1"
        assert ChaptersProcessor._label_from_filename("book2_chapter_10") == "Chapter 10"

    def test_no_digits_uses_stem(self) -> None:
        assert ChaptersProcessor._label_from_filename("titlepage") == "Titlepage"
        assert ChaptersProcessor._label_from_filename("story") == "Story"

    def test_underscores_replaced_with_spaces(self) -> None:
        assert ChaptersProcessor._label_from_filename("index_split_000") == "Chapter 0"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestLabelFromFilename -v
```

Expected: `AttributeError: type object 'ChaptersProcessor' has no attribute '_label_from_filename'`

- [ ] **Step 3: Implement `_label_from_filename`**

Add to `ChaptersProcessor` in `src/boozarr/processors/chapters.py`, after the `_no_chapters_issue` method (line ~95):

```python
@staticmethod
def _label_from_filename(stem: str) -> str:
    """Extract a human-readable chapter label from a filename stem.

    Trailing digits become 'Chapter N' (stripping leading zeros).
    Stems without digits are cleaned up (underscores → spaces, title-cased).
    """
    match = re.search(r"(\d+)$", stem)
    if match:
        num = int(match.group(1))
        return f"Chapter {num}"
    label = stem.replace("_", " ").strip()
    if label:
        label = label[0].upper() + label[1:]
    return label if label else "Chapter"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestLabelFromFilename -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_processors/test_chapters.py src/boozarr/processors/chapters.py
git commit -m "feat: add _label_from_filename helper for chapter labels"
```

---

### Task 2: `_resolve_spine_order` helper

**Files:**
- Modify: `src/boozarr/processors/chapters.py` (add new method)
- Test: `tests/test_processors/test_chapters.py` (add test class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_processors/test_chapters.py`:

```python
class TestResolveSpineOrder:
    """Tests for _resolve_spine_order helper."""

    def test_returns_spine_order_map(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        (extract_dir / "OEBPS").mkdir(parents=True)
        opf_path = "OEBPS/content.opf"
        opf_content = (
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf">'
            '<manifest>'
            '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest>'
            '<spine>'
            '<itemref idref="cover"/>'
            '<itemref idref="ch1"/>'
            '<itemref idref="ch2"/>'
            '</spine>'
            '</package>'
        )
        (extract_dir / opf_path).write_text(opf_content)
        (extract_dir / "OEBPS/chapter1.xhtml").write_text("<html/>")
        (extract_dir / "OEBPS/chapter2.xhtml").write_text("<html/>")
        (extract_dir / "OEBPS/cover.xhtml").write_text("<html/>")

        order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)

        assert order == {
            "OEBPS/cover.xhtml": 0,
            "OEBPS/chapter1.xhtml": 1,
            "OEBPS/chapter2.xhtml": 2,
        }

    def test_handles_root_opf_path(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest><item id="ch" href="ch.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="ch"/></spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)
        (extract_dir / "ch.xhtml").write_text("<html/>")

        order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)

        assert order == {"ch.xhtml": 0}

    def test_skips_missing_idref(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest><item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine>'
            '<itemref idref="missing"/>'
            '<itemref idref="ch1"/>'
            '</spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)

        order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)

        assert order == {"ch1.xhtml": 0}  # missing idref skipped, ch1 becomes position 0

    def test_returns_empty_on_corrupt_xml(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        (extract_dir / opf_path).write_text("not valid xml <<<")

        order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)

        assert order == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestResolveSpineOrder -v
```

Expected: `AttributeError: ... _resolve_spine_order`

- [ ] **Step 3: Implement `_resolve_spine_order`**

Add to `ChaptersProcessor`, after `_label_from_filename`:

```python
@staticmethod
def _resolve_spine_order(extract_dir: Path, opf_path: str) -> dict[str, int]:
    """Parse OPF spine to get file reading order.

    Returns:
        Mapping from file path (relative to extract_dir) to zero-based spine
        position.  Empty dict on parse failure or missing spine.
    """
    opf_file = extract_dir / opf_path
    try:
        root = ElementTree.parse(str(opf_file)).getroot()
    except Exception:
        return {}

    # Build {id: href} from manifest items
    manifest: dict[str, str] = {}
    for element in root.iter():
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        if tag == "item":
            item_id = element.get("id")
            href = element.get("href")
            if item_id and href:
                manifest[item_id] = href

    # Resolve named entities that ElementTree may expand
    namespace = ""
    for _tag in root.iter():
        if "}" in _tag.tag:
            namespace = "{" + _tag.tag.split("}")[0][1:] + "}"
            break

    # Build ordered dict from spine itemrefs
    order: dict[str, int] = {}
    opf_dir = str(Path(opf_path).parent)
    for element in root.iter(f"{namespace}spine"):
        for itemref in element:
            idref = itemref.get("idref")
            if idref and idref in manifest:
                href = manifest[idref]
                resolved = str(Path(opf_dir) / href) if opf_dir != "." else href
                if resolved not in order:
                    order[resolved] = len(order)

    # Fallback: scan all itemref elements if namespace-specific lookup failed
    if not order:
        for element in root.iter():
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
            if tag == "itemref":
                idref = element.get("idref")
                if idref and idref in manifest:
                    href = manifest[idref]
                    resolved = str(Path(opf_dir) / href) if opf_dir != "." else href
                    if resolved not in order:
                        order[resolved] = len(order)

    return order
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestResolveSpineOrder -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_processors/test_chapters.py src/boozarr/processors/chapters.py
git commit -m "feat: add _resolve_spine_order helper for OPF spine parsing"
```

---

### Task 3: `_discover_from_spine` spine-based fallback

**Files:**
- Modify: `src/boozarr/processors/chapters.py` (add new method)
- Test: `tests/test_processors/test_chapters.py` (add test class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_processors/test_chapters.py`:

```python
class TestDiscoverFromSpine:
    """Tests for _discover_from_spine fallback."""

    def test_discovers_from_spine_items(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        (extract_dir / "OEBPS").mkdir(parents=True)
        opf_path = "OEBPS/content.opf"
        opf_content = (
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf">'
            '<manifest>'
            '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ch3" href="chapter3.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest>'
            '<spine>'
            '<itemref idref="ch1"/>'
            '<itemref idref="ch2"/>'
            '<itemref idref="ch3"/>'
            '</spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)
        (extract_dir / "OEBPS/chapter1.xhtml").write_text("<html><body>text</body></html>" * 50)
        (extract_dir / "OEBPS/chapter2.xhtml").write_text("<html><body>text</body></html>" * 50)
        (extract_dir / "OEBPS/chapter3.xhtml").write_text("<html><body>text</body></html>" * 50)

        discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)

        assert len(discovered) == 3
        assert discovered[0] == ("OEBPS/chapter1.xhtml", "Chapter 1")
        assert discovered[1] == ("OEBPS/chapter2.xhtml", "Chapter 2")
        assert discovered[2] == ("OEBPS/chapter3.xhtml", "Chapter 3")

    def test_filters_non_content_files(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="title" href="titlepage.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="cr" href="copyright.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="about" href="about.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest>'
            '<spine>'
            '<itemref idref="cover"/>'
            '<itemref idref="title"/>'
            '<itemref idref="toc"/>'
            '<itemref idref="nav"/>'
            '<itemref idref="cr"/>'
            '<itemref idref="about"/>'
            '<itemref idref="ch1"/>'
            '</spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)
        for name in ["cover.xhtml", "titlepage.xhtml", "toc.xhtml", "nav.xhtml",
                       "copyright.xhtml", "about.xhtml", "chapter1.xhtml"]:
            (extract_dir / name).write_text("<html><body>text</body></html>" * 50)

        discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)

        assert len(discovered) == 1
        assert discovered[0][0] == "chapter1.xhtml"

    def test_filters_small_files(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="tiny" href="tiny.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="big" href="big.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest>'
            '<spine><itemref idref="tiny"/><itemref idref="big"/></spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)
        (extract_dir / "tiny.xhtml").write_text("small")  # < 2KB
        (extract_dir / "big.xhtml").write_text("x" * 3000)  # > 2KB

        discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)

        assert len(discovered) == 1
        assert discovered[0][0] == "big.xhtml"

    def test_returns_empty_on_spine_parse_failure(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = "content.opf"
        (extract_dir / opf_path).write_text("<<<garbage>>>")

        discovered = ChaptersProcessor._discover_from_spine(extract_dir, opf_path)

        assert discovered == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestDiscoverFromSpine -v
```

Expected: `AttributeError: ... _discover_from_spine`

- [ ] **Step 3: Implement `_discover_from_spine`**

Add to `ChaptersProcessor`, after `_resolve_spine_order`:

```python
_SKIP_FILENAME_SUBSTRINGS: tuple[str, ...] = (
    "cover", "title", "toc", "nav", "copyright", "about",
)
_SMALL_FILE_THRESHOLD: int = 2048

@staticmethod
def _discover_from_spine(extract_dir: Path, opf_path: str) -> list[tuple[str, str]]:
    """Generate chapter entries from the OPF spine reading order.

    Only called when _discover_chapters finds zero text-pattern matches.
    Filters out non-content files via smart heuristics and labels each
    remaining file by extracting trailing digits from its stem.
    """
    order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)
    if not order:
        return []

    discovered: list[tuple[str, str]] = []
    for file_path in order:
        full_path = extract_dir / file_path
        if not full_path.is_file():
            continue

        stem = full_path.stem.lower()
        if any(p in stem for p in ChaptersProcessor._SKIP_FILENAME_SUBSTRINGS):
            continue

        try:
            if full_path.stat().st_size < ChaptersProcessor._SMALL_FILE_THRESHOLD:
                continue
        except OSError:
            continue

        label = ChaptersProcessor._label_from_filename(full_path.stem)
        discovered.append((file_path, label))

    return discovered
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestDiscoverFromSpine -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_processors/test_chapters.py src/boozarr/processors/chapters.py
git commit -m "feat: add _discover_from_spine fallback for zero-marker EPUBs"
```

---

### Task 4: Multi-match `_discover_chapters` rewrite

**Files:**
- Modify: `src/boozarr/processors/chapters.py:99-119` (rewrite `_discover_chapters`)
- Test: `tests/test_processors/test_chapters.py` (add test class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_processors/test_chapters.py`:

```python
class TestDiscoverChaptersMultiMatch:
    """Tests for multi-match _discover_chapters."""

    def test_finds_all_chapter_markers_in_file(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapters.xhtml"
        content = "<html><body>"
        for i in range(1, 11):
            content += f"<p>CHAPTER {i}</p>\n"
        content += "</body></html>"
        xhtml.write_text(content)

        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest><item id="ch" href="chapters.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="ch"/></spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)

        discovered = ChaptersProcessor._discover_chapters(extract_dir, opf_path)

        assert len(discovered) == 10
        assert all(m[0] == "chapters.xhtml" for m in discovered)
        assert discovered[0][1] == "CHAPTER 1"
        assert discovered[4][1] == "CHAPTER 5"
        assert discovered[9][1] == "CHAPTER 10"

    def test_finds_mixed_patterns_in_file(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "book.xhtml"
        content = (
            "<html><body>"
            "<p>Part I</p>"
            "<p>Chapter 1</p>"
            "<p>Chapter 2</p>"
            "<p>Section 1</p>"
            "</body></html>"
        )
        xhtml.write_text(content)

        discovered = ChaptersProcessor._discover_chapters(extract_dir)

        labels = [m[1] for m in discovered]
        assert "Part I" in labels
        assert "Chapter 1" in labels
        assert "Chapter 2" in labels
        assert "Section 1" in labels

    def test_dedup_overlapping_patterns(self, tmp_path: Path) -> None:
        """CHAPTER 1 matches BOTH Chapter\s+\d+ and CHAPTER\s+\w+ — dedup to one."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapters.xhtml"
        content = "<html><body><p>CHAPTER 1</p></body></html>"
        xhtml.write_text(content)

        discovered = ChaptersProcessor._discover_chapters(extract_dir)

        assert len(discovered) == 1
        assert discovered[0][1] == "CHAPTER 1"

    def test_h1_fallback_when_no_pattern_matches(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "story.xhtml"
        content = "<html><body><h1>The Journey Begins</h1><p>Once upon a time...</p></body></html>"
        xhtml.write_text(content)

        discovered = ChaptersProcessor._discover_chapters(extract_dir)

        assert len(discovered) == 1
        assert discovered[0][1] == "The Journey Begins"

    def test_no_h1_fallback_when_pattern_already_matched(self, tmp_path: Path) -> None:
        """If Chapter\s+\d+ matches, don't ALSO emit an h1 entry for the same file."""
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "chapter.xhtml"
        content = "<html><body><h1>Book Title</h1><p>Chapter 1</p></body></html>"
        xhtml.write_text(content)

        discovered = ChaptersProcessor._discover_chapters(extract_dir)

        labels = [m[1] for m in discovered]
        assert "Chapter 1" in labels
        assert "Book Title" not in labels  # h1 skipped because pattern matched

    def test_returns_empty_when_no_markers_and_no_headings(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml = extract_dir / "blank.xhtml"
        content = "<html><body><p>Just some text, nothing structured.</p></body></html>"
        xhtml.write_text(content)

        discovered = ChaptersProcessor._discover_chapters(extract_dir)

        assert discovered == []

    def test_sorts_by_spine_order_when_opf_available(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        xhtml1 = extract_dir / "middle.xhtml"
        xhtml1.write_text("<html><body><p>Chapter 1</p></body></html>")
        xhtml2 = extract_dir / "first.xhtml"
        xhtml2.write_text("<html><body><p>Prologue</p></body></html>")
        xhtml3 = extract_dir / "last.xhtml"
        xhtml3.write_text("<html><body><p>Epilogue</p></body></html>")
        opf_path = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="f" href="first.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="m" href="middle.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="l" href="last.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest>'
            '<spine>'
            '<itemref idref="f"/><itemref idref="m"/><itemref idref="l"/>'
            '</spine></package>'
        )
        (extract_dir / opf_path).write_text(opf_content)

        discovered = ChaptersProcessor._discover_chapters(extract_dir, opf_path)

        assert discovered[0][1] == "Prologue"  # first in spine
        assert discovered[1][1] == "Chapter 1"  # middle in spine
        assert discovered[2][1] == "Epilogue"  # last in spine
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestDiscoverChaptersMultiMatch -v
```

Expected: some tests may pass (existing behavior handles single match per file), but tests like `test_finds_all_chapter_markers_in_file` should FAIL because current code only finds "CHAPTER 1" (first match, not 10).

- [ ] **Step 3: Rewrite `_discover_chapters` for multi-match**

Replace the existing `_discover_chapters` method (lines 99-119) in `src/boozarr/processors/chapters.py`:

```python
@staticmethod
def _discover_chapters(
    extract_dir: Path, opf_path: str | None = None
) -> list[tuple[str, str]]:
    """Scan XHTML files for chapter patterns and h1/h2 fallback.

    Returns all matches across all pattern types, deduplicated by
    (file_path, byte_offset).  Sorted by spine order when opf_path
    is provided, otherwise by file path alphabetically.
    """
    discovered: list[tuple[str, str]] = []
    seen: set[tuple[str, int]] = set()

    for xhtml_file in sorted(extract_dir.rglob("*.xhtml")):
        if not xhtml_file.is_file():
            continue
        try:
            content = xhtml_file.read_text(encoding="utf-8")
        except Exception:
            continue
        rel_path = str(xhtml_file.relative_to(extract_dir))

        matched = False
        for pattern in _CHAPTER_PATTERNS:
            for match in pattern.finditer(content):
                pos = match.start()
                if (rel_path, pos) not in seen:
                    discovered.append((rel_path, match.group(0)))
                    seen.add((rel_path, pos))
                matched = True

        if not matched:
            h_match = re.search(
                r"<h[12][^>]*>(.+?)</h[12]>", content, re.IGNORECASE
            )
            if h_match:
                discovered.append((rel_path, h_match.group(1).strip()))

    if opf_path is not None and discovered:
        return _sort_by_spine_order(discovered, extract_dir, opf_path)
    return discovered
```

Add `_sort_by_spine_order` as a module-level helper after `_discover_chapters`
(alongside `_CHAPTER_PATTERNS` and other module helpers):

```python
def _sort_by_spine_order(
    discovered: list[tuple[str, str]], extract_dir: Path, opf_path: str
) -> list[tuple[str, str]]:
    """Sort discovered entries by OPF spine reading order."""
    order = ChaptersProcessor._resolve_spine_order(extract_dir, opf_path)
    if not order:
        return discovered

    def _key(item: tuple[str, str]) -> tuple[int, str]:
        return (order.get(item[0], 999_999), item[0])

    return sorted(discovered, key=_key)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestDiscoverChaptersMultiMatch -v
```

Expected: all 7 tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd /data/boozarr && uv run pytest tests/ -v
```

Expected: all existing tests still pass (existing tests call `_discover_chapters` with only `extract_dir` — the `opf_path=None` default makes this backward-compatible).

- [ ] **Step 6: Commit**

```bash
git add tests/test_processors/test_chapters.py src/boozarr/processors/chapters.py
git commit -m "feat: rewrite _discover_chapters for multi-match + spine sorting"
```

---

### Task 5: Wire spine fallback into `fix()`

**Files:**
- Modify: `src/boozarr/processors/chapters.py:150-170` (`fix()` method)
- Test: `tests/test_processors/test_chapters.py` (add test class)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_processors/test_chapters.py`:

```python
class TestFixSpineFallbackIntegration:
    """Integration tests verifying fix() uses spine fallback when needed."""

    def test_fix_uses_spine_fallback_for_no_marker_epub(self, tmp_path: Path) -> None:
        """EPUB with no text markers should fall back to spine-based discovery."""
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
                '<manifest>'
                '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>'
                '</manifest>'
                '<spine><itemref idref="ch1"/><itemref idref="ch2"/></spine></package>',
            )
            # No chapter text, no headings — just plain text
            zf.writestr("chapter1.xhtml", "<html><body><p>It was a dark and stormy night.</p></body></html>" * 50)
            zf.writestr("chapter2.xhtml", "<html><body><p>The story continues.</p></body></html>" * 50)

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = ChaptersProcessor()
        issues = processor.check(wrapper)
        assert len(issues) == 1  # no NCX

        fixes = processor.fix(wrapper, issues, {})
        assert len(fixes) == 1
        assert "2 entries" in fixes[0].new_value or "entries" in fixes[0].description

    def test_fix_has_chapters_after_repack(self, tmp_path: Path) -> None:
        """After fix() writes NCX, re-reading should show zero issues."""
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
                '<manifest>'
                '<item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
                '</manifest>'
                '<spine><itemref idref="ch"/></spine></package>',
            )
            zf.writestr("chapter.xhtml", "<html><body><p>Once upon a time...</p></body></html>" * 50)

        wrapper = EpubWrapper(epub_path)
        extract_dir = tmp_path / "extracted"
        wrapper.extract(extract_dir)

        processor = ChaptersProcessor()
        issues = processor.check(wrapper)
        assert len(issues) == 1

        fixes = processor.fix(wrapper, issues, {})
        assert len(fixes) == 1

        wrapper.repack(epub_path)
        wrapper2 = EpubWrapper(epub_path)
        issues_after = processor.check(wrapper2)
        assert len(issues_after) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestFixSpineFallbackIntegration -v
```

Expected: FAIL — `fix()` returns empty list because `_discover_chapters` finds nothing and spine fallback is not wired.

- [ ] **Step 3: Wire spine fallback into `fix()`**

Modify the `fix()` method in `src/boozarr/processors/chapters.py` (lines 150-170).  The key change is bracketed by comments:

```python
def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
    """Generate an NCX file from XHTML headings and write it to the EPUB."""
    extract_dir = getattr(epub, "_extract_dir", None)
    if extract_dir is None:
        return []

    try:
        opf_path = epub.get_opf_path()
    except Exception:
        opf_path = None

    discovered = self._discover_chapters(extract_dir, opf_path)

    # --- NEW: spine fallback when patterns find nothing ---
    if not discovered and opf_path is not None:
        discovered = self._discover_from_spine(extract_dir, opf_path)
    # --- end new block ---

    if not discovered:
        return []

    ncx_rel = "toc.ncx"
    for f in extract_dir.rglob("*.ncx"):
        ncx_rel = str(f.relative_to(extract_dir))

    ncx_path = extract_dir / ncx_rel
    self._write_ncx(ncx_path, discovered)

    return [
        Fix(
            self.name,
            ncx_rel,
            f"Added {len(discovered)} chapter entries to {ncx_rel}",
            old_value="",
            new_value=f"<navMap>{len(discovered)} entries</navMap>",
        )
    ]
```

The `try/except` around `epub.get_opf_path()` handles the case where mock objects or corrupt EPUBs raise on this call — `opf_path` stays `None` and spine fallback is skipped.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_chapters.py::TestFixSpineFallbackIntegration -v
```

Expected: both tests PASS

- [ ] **Step 5: Run full test suite**

```bash
cd /data/boozarr && uv run pytest tests/ -v
```

Expected: all existing + new tests PASS

- [ ] **Step 6: Run quality gates**

```bash
cd /data/boozarr && uv run ruff check --fix . && uv run ruff format . && uv run mypy . && uv run pytest --no-cov -q
```

Expected: 0 ruff errors, 0 mypy errors, all tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_processors/test_chapters.py src/boozarr/processors/chapters.py
git commit -m "feat: wire _discover_from_spine fallback into chapters fix()"
```

---

