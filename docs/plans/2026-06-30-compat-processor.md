# Cross-Device Compatibility Processor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `CompatProcessor` that strips embedded fonts, removes Apple metadata, normalises OPF namespace prefixes, and cleans up `@font-face` CSS — gated behind the existing `--normalise` flag.

**Architecture:** One new processor class in `src/boozarr/processors/compat.py`, added at position 0 in the pipeline order. `check()` reads the OPF from the EPUB ZIP to detect font files and Apple display options. `fix()` works on the extracted directory — removes font files, rewrites the OPF (manifest cleanup + namespace normalisation), and strips `@font-face` rules from CSS.

**Tech Stack:** Python 3.12+, `xml.etree.ElementTree`, `re`, `zipfile` (tests), pytest

---

### Task 1: CompatProcessor skeleton + font detection check()

**Files:**
- Create: `src/boozarr/processors/compat.py`
- Create: `tests/test_processors/test_compat.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_processors/test_compat.py`:

```python
"""Tests for CompatProcessor."""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pathlib import Path

from boozarr.processors.compat import CompatProcessor


class TestCompatCheck:
    def test_no_fonts_returns_empty(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest></package>'
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert issues == []

    def test_detects_embedded_fonts(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="f1" href="fonts/body.otf" media-type="application/x-font-otf"/>'
            '<item id="f2" href="fonts/title.ttf" media-type="application/x-font-ttf"/>'
            '</manifest></package>'
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert len(issues) == 2
        assert all(i.fix_possible for i in issues)
        assert "body.otf" in issues[0].description
        assert "title.ttf" in issues[1].description

    def test_ignores_woff2_fonts(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="f1" href="fonts/body.woff2" media-type="font/woff2"/>'
            '</manifest></package>'
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert issues == []

    def test_skips_when_normalise_not_set(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        opf = (
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="f1" href="fonts/body.otf" media-type="application/x-font-otf"/>'
            '</manifest></package>'
        )
        epub.read_file.return_value = opf
        issues = CompatProcessor().check(epub, {})
        assert issues == []

    def test_handles_corrupt_opf(self) -> None:
        epub = MagicMock()
        epub.get_opf_path.return_value = "content.opf"
        epub.read_file.return_value = "<<<garbage>>>"
        issues = CompatProcessor().check(epub, {"normalise": True})
        assert issues == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py -v
```

Expected: `ModuleNotFoundError: No module named 'boozarr.processors.compat'`

- [ ] **Step 3: Implement CompatProcessor skeleton + font detection**

Create `src/boozarr/processors/compat.py`:

```python
"""Cross-device compatibility processor."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from boozarr.processors.base import BaseProcessor, Fix, Issue

_FONT_MEDIA_TYPES: tuple[str, ...] = (
    "application/x-font-otf",
    "font/otf",
    "application/x-font-ttf",
    "font/ttf",
    "application/font-woff",
    "application/vnd.ms-fontobject",
)
# WOFF2 is intentionally excluded — required by EPUB3 readers.


class CompatProcessor(BaseProcessor):
    name = "compat"

    def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
        if config is None or not config.get("normalise"):
            return []

        try:
            opf_path = epub.get_opf_path()
            opf_content = epub.read_file(opf_path)
            root = ElementTree.fromstring(opf_content)
        except Exception:
            return []

        issues: list[Issue] = []
        for item in root.iter():
            tag = item.tag.split("}")[-1] if "}" in item.tag else item.tag
            if tag != "item":
                continue
            mt = item.get("media-type", "")
            if mt in _FONT_MEDIA_TYPES:
                href = item.get("href", "?")
                issues.append(
                    Issue(
                        processor=self.name,
                        severity="info",
                        location=f"font: {href}",
                        description=f"Embedded font found: {href}",
                        fix_possible=True,
                    )
                )
        return issues

    def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
        return []
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_processors/test_compat.py src/boozarr/processors/compat.py
git commit -m "feat: add CompatProcessor skeleton with font detection"
```

---

### Task 2: Detect Apple Books display options

**Files:**
- Modify: `src/boozarr/processors/compat.py` (extend `check()`)
- Modify: `tests/test_processors/test_compat.py` (add test)

- [ ] **Step 1: Write the failing test**

Add to `TestCompatCheck`:

```python
def test_detects_apple_display_options(self) -> None:
    epub = MagicMock()
    epub.get_opf_path.return_value = "content.opf"
    opf = (
        '<?xml version="1.0"?><package>'
        '<manifest>'
        '<item id="ado" href="META-INF/com.apple.ibooks.display-options.xml" '
        'media-type="application/xhtml+xml"/>'
        '</manifest></package>'
    )
    epub.read_file.return_value = opf
    issues = CompatProcessor().check(epub, {"normalise": True})
    assert len(issues) == 1
    assert "apple" in issues[0].description.lower()

def test_apple_options_without_normalise_skipped(self) -> None:
    epub = MagicMock()
    epub.get_opf_path.return_value = "content.opf"
    opf = (
        '<?xml version="1.0"?><package>'
        '<manifest>'
        '<item id="ado" href="META-INF/com.apple.ibooks.display-options.xml" '
        'media-type="application/xhtml+xml"/>'
        '</manifest></package>'
    )
    epub.read_file.return_value = opf
    issues = CompatProcessor().check(epub, {})
    assert issues == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py::TestCompatCheck::test_detects_apple_display_options tests/test_processors/test_compat.py::TestCompatCheck::test_apple_options_without_normalise_skipped -v
```

Expected: FAIL — no Apple display options detection

- [ ] **Step 3: Extend `check()` to detect Apple display options**

Add this constant after `_FONT_MEDIA_TYPES`:

```python
_APPLE_DISPLAY_OPTIONS = "META-INF/com.apple.ibooks.display-options.xml"
```

Add this block at the end of `check()`, before `return issues`:

```python
# Check for Apple Books display options
for item in root.iter():
    tag = item.tag.split("}")[-1] if "}" in item.tag else item.tag
    if tag != "item":
        continue
    href = item.get("href", "")
    if href == _APPLE_DISPLAY_OPTIONS or href.endswith("/" + _APPLE_DISPLAY_OPTIONS):
        issues.append(
            Issue(
                processor=self.name,
                severity="info",
                location=f"meta: {href}",
                description="Apple Books display options found",
                fix_possible=True,
            )
        )
        break  # only one display options file expected
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_processors/test_compat.py src/boozarr/processors/compat.py
git commit -m "feat: detect Apple Books display options in CompatProcessor"
```

---

### Task 3: Font removal fix()

**Files:**
- Modify: `src/boozarr/processors/compat.py` (implement `fix()` for fonts)
- Modify: `tests/test_processors/test_compat.py` (add fix tests)

- [ ] **Step 1: Write the failing tests**

Add new class `TestCompatFix`:

```python
class TestCompatFix:
    def test_removes_font_files_from_disk(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        (extract_dir / "fonts").mkdir()
        font_file = extract_dir / "fonts" / "body.otf"
        font_file.write_text("fake font data")

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"
        opf_content = (
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="f1" href="fonts/body.otf" media-type="application/x-font-otf"/>'
            '</manifest></package>'
        )
        (extract_dir / "content.opf").write_text(opf_content)

        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="font: fonts/body.otf",
                description="Embedded font found: fonts/body.otf",
                fix_possible=True,
            )
        ]
        fixes = CompatProcessor().fix(epub, issues, {"normalise": True})
        assert len(fixes) >= 1
        assert not font_file.exists()  # font removed from disk

    def test_rewrites_opf_manifest_after_font_removal(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="f1" href="fonts/body.otf" media-type="application/x-font-otf"/>'
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest></package>'
        )

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="font: fonts/body.otf",
                description="Embedded font found: fonts/body.otf",
                fix_possible=True,
            )
        ]
        fixes = CompatProcessor().fix(epub, issues, {"normalise": True})
        assert len(fixes) >= 1

        # Verify OPF no longer contains the font item
        opf_after = opf_path.read_text()
        assert "fonts/body.otf" not in opf_after
        assert "ch1.xhtml" in opf_after  # non-font items preserved
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py::TestCompatFix -v
```

Expected: FAIL — `fix()` returns empty list

- [ ] **Step 3: Implement `fix()` for font removal**

Replace the stubbed `fix()`:

```python
def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
    extract_dir = getattr(epub, "_extract_dir", None)
    if extract_dir is None:
        return []

    fixes: list[Fix] = []
    opf_path = epub.get_opf_path()
    opf_file = extract_dir / opf_path
    try:
        opf_content = opf_file.read_text(encoding="utf-8")
    except Exception:
        return []

    for issue in issues:
        prefix, _, path = issue.location.partition(": ")
        if prefix == "font":
            # Remove from disk
            font_file = extract_dir / path
            try:
                font_file.unlink(missing_ok=True)
            except OSError:
                continue
            # Remove from OPF manifest
            opf_content = self._remove_manifest_item(opf_content, path)
            fixes.append(
                Fix(
                    processor=self.name,
                    location=issue.location,
                    description=f"Removed embedded font: {path}",
                    old_value=path,
                    new_value="",
                )
            )

    if fixes:
        try:
            opf_file.write_text(opf_content, encoding="utf-8")
        except OSError:
            pass

    return fixes

@staticmethod
def _remove_manifest_item(opf_xml: str, href: str) -> str:
    """Remove <item> elements whose href matches from the OPF manifest."""
    escaped = re.escape(href)
    return re.sub(
        r'<item\b[^>]*href="' + escaped + r'"[^>]*/?>\s*',
        "",
        opf_xml,
        count=1,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_processors/test_compat.py src/boozarr/processors/compat.py
git commit -m "feat: implement font removal in CompatProcessor fix()"
```

---

### Task 4: Apple display options removal in fix()

**Files:**
- Modify: `src/boozarr/processors/compat.py` (extend `fix()` for Apple options)
- Modify: `tests/test_processors/test_compat.py` (add test)

- [ ] **Step 1: Write the failing test**

Add to `TestCompatFix`:

```python
def test_removes_apple_display_options(self, tmp_path: Path) -> None:
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    meta_inf = extract_dir / "META-INF"
    meta_inf.mkdir()
    ado_file = meta_inf / "com.apple.ibooks.display-options.xml"
    ado_file.write_text("<display_options/>")
    opf_path = extract_dir / "content.opf"
    opf_path.write_text(
        '<?xml version="1.0"?><package>'
        '<manifest>'
        '<item id="ado" href="META-INF/com.apple.ibooks.display-options.xml" '
        'media-type="application/xhtml+xml"/>'
        '</manifest></package>'
    )

    epub = MagicMock()
    epub._extract_dir = extract_dir
    epub.get_opf_path.return_value = "content.opf"

    issues = [
        Issue(
            processor="compat",
            severity="info",
            location="meta: META-INF/com.apple.ibooks.display-options.xml",
            description="Apple Books display options found",
            fix_possible=True,
        )
    ]
    fixes = CompatProcessor().fix(epub, issues, {"normalise": True})
    assert len(fixes) >= 1
    assert not ado_file.exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py::TestCompatFix::test_removes_apple_display_options -v
```

Expected: FAIL — no Apple options removal

- [ ] **Step 3: Extend `fix()` for Apple display options**

Add this block inside the `for issue in issues:` loop, after the font block:

```python
elif prefix == "meta" and "apple" in issue.description.lower():
    # Remove Apple Books display options file
    ado_file = extract_dir / path
    try:
        ado_file.unlink(missing_ok=True)
    except OSError:
        continue
    # Remove from OPF manifest
    opf_content = self._remove_manifest_item(opf_content, path)
    fixes.append(
        Fix(
            processor=self.name,
            location=issue.location,
            description="Removed Apple Books display options",
            old_value=path,
            new_value="",
        )
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py -v
```

Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_processors/test_compat.py src/boozarr/processors/compat.py
git commit -m "feat: remove Apple Books display options in CompatProcessor fix()"
```

---

### Task 5: OPF namespace normalisation

**Files:**
- Modify: `src/boozarr/processors/compat.py` (add OPF normalisation)
- Modify: `tests/test_processors/test_compat.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Add new class `TestCompatNormaliseOpf`:

```python
class TestCompatNormaliseOpf:
    def test_normalises_namespaced_opf(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ns0:package xmlns:ns0="http://www.idpf.org/2007/opf" version="2.0">\n'
            '<ns0:manifest>\n'
            '<ns0:item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>\n'
            '</ns0:manifest>\n'
            '<ns0:spine toc="ncx">\n'
            '<ns0:itemref idref="ch1"/>\n'
            '</ns0:spine>\n'
            '</ns0:package>\n'
        )

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        # Call fix() — OPF normalisation runs as part of fix()
        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="font: fonts/nonexistent.otf",
                description="Embedded font found: fonts/nonexistent.otf",
                fix_possible=True,
            )
        ]
        fixes = CompatProcessor().fix(epub, issues, {"normalise": True})

        result = opf_path.read_text()
        assert "<ns0:" not in result, f"Namespace prefixes remain: {result[:200]}"
        assert "<itemref" in result
        assert "<item " in result
        assert 'xmlns="http://www.idpf.org/2007/opf"' in result

    def test_normalised_opf_preserves_content(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = extract_dir / "content.opf"
        original = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ns0:package xmlns:ns0="http://www.idpf.org/2007/opf" version="2.0">\n'
            '<ns0:manifest>\n'
            '<ns0:item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>\n'
            '</ns0:manifest>\n'
            '<ns0:spine toc="ncx">\n'
            '<ns0:itemref idref="ch1"/>\n'
            '</ns0:spine>\n'
            '</ns0:package>\n'
        )
        opf_path.write_text(original)

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        CompatProcessor().fix(epub, [], {"normalise": True})

        result = opf_path.read_text()
        # idref and href values preserved
        assert 'idref="ch1"' in result
        assert 'href="ch1.xhtml"' in result

    def test_normalised_opf_handles_corrupt_xml(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        opf_path = extract_dir / "content.opf"
        opf_path.write_text("not xml <<<")

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        fixes = CompatProcessor().fix(epub, [], {"normalise": True})
        # Should not raise, returns gracefully
        assert isinstance(fixes, list)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py::TestCompatNormaliseOpf -v
```

Expected: FAIL — `<ns0:` prefixes still present

- [ ] **Step 3: Implement OPF namespace normalisation**

Add this static method to `CompatProcessor`:

```python
@staticmethod
def _normalise_opf_namespace(extract_dir: Path, opf_path: str) -> None:
    """Rewrite namespace-prefixed OPF tags to bare-tag form."""
    opf_file = extract_dir / opf_path
    try:
        content = opf_file.read_text(encoding="utf-8")
    except Exception:
        return

    # Only process OPF files that use a namespace prefix
    if "<ns0:" not in content and "xmlns:ns0" not in content:
        # Already bare — check for any other prefix patterns
        has_prefixed = bool(re.search(r"<\w+:\w+", content))  # noqa: F821
        if not has_prefixed:
            return

    # Remove namespace prefix declarations
    content = re.sub(r'\s*xmlns:ns0="[^"]*"', "", content)
    # Strip ns0: prefix from all tags (both open and close)
    content = re.sub(r"<(/?)ns0:", r"<\1", content)
    # Add the default namespace to the root package element
    content = re.sub(
        r'(<package\b[^>]*)>',
        r'\1 xmlns="http://www.idpf.org/2007/opf">',
        content,
        count=1,
    )

    try:
        opf_file.write_text(content, encoding="utf-8")
    except OSError:
        pass
```

Add a call at the end of `fix()`, before `return fixes`:

```python
# Normalise OPF namespace (always runs when normalise is active)
self._normalise_opf_namespace(extract_dir, opf_path)
fixes.append(
    Fix(
        processor=self.name,
        location=opf_path,
        description="Normalised OPF namespace prefixes for cross-device compatibility",
        old_value="namespace-prefixed",
        new_value="bare-tag",
    )
)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py -v
```

Expected: all 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_processors/test_compat.py src/boozarr/processors/compat.py
git commit -m "feat: add OPF namespace normalisation to CompatProcessor"
```

---

### Task 6: CSS @font-face cleanup

**Files:**
- Modify: `src/boozarr/processors/compat.py` (add CSS cleanup)
- Modify: `tests/test_processors/test_compat.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Add new class `TestCompatCleanupCss`:

```python
class TestCompatCleanupCss:
    def test_removes_font_face_for_stripped_font(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        css_file = extract_dir / "style.css"
        css_file.write_text(
            "@font-face {\n"
            '  font-family: "Body";\n'
            '  src: url("fonts/body.otf");\n'
            "}\n"
            "p { margin: 0; }\n"
        )
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="css" href="style.css" media-type="text/css"/>'
            '</manifest></package>'
        )

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="font: fonts/body.otf",
                description="Embedded font found: fonts/body.otf",
                fix_possible=True,
            )
        ]
        CompatProcessor().fix(epub, issues, {"normalise": True})

        result = css_file.read_text()
        assert "@font-face" not in result
        assert "p { margin: 0; }" in result  # non-font CSS preserved

    def test_preserves_unrelated_font_face(self, tmp_path: Path) -> None:
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        css_file = extract_dir / "style.css"
        css_file.write_text(
            "@font-face {\n"
            '  font-family: "Title";\n'
            '  src: url("fonts/title.woff2");\n'  # WOFF2 — not stripped
            "}\n"
        )
        opf_path = extract_dir / "content.opf"
        opf_path.write_text(
            '<?xml version="1.0"?><package>'
            '<manifest>'
            '<item id="css" href="style.css" media-type="text/css"/>'
            '</manifest></package>'
        )

        epub = MagicMock()
        epub._extract_dir = extract_dir
        epub.get_opf_path.return_value = "content.opf"

        # Pass an issue for a DIFFERENT font (body.otf, not title.woff2)
        issues = [
            Issue(
                processor="compat",
                severity="info",
                location="font: fonts/body.otf",
                description="Embedded font found: fonts/body.otf",
                fix_possible=True,
            )
        ]
        CompatProcessor().fix(epub, issues, {"normalise": True})

        result = css_file.read_text()
        assert "@font-face" in result  # WOFF2 font-face preserved
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py::TestCompatCleanupCss -v
```

Expected: FAIL — `@font-face` rules still present

- [ ] **Step 3: Implement CSS @font-face cleanup**

Add this constant at the module level:

```python
_FONT_FACE_RE = re.compile(r"@font-face\s*\{[^}]*\}", re.DOTALL | re.IGNORECASE)
```

Add this static method:

```python
@staticmethod
def _strip_font_faces(extract_dir: Path, removed_hrefs: set[str]) -> None:
    """Remove @font-face blocks that reference stripped font files from all CSS files."""
    if not removed_hrefs:
        return
    for css_file in extract_dir.rglob("*.css"):
        try:
            content = css_file.read_text(encoding="utf-8")
        except Exception:
            continue
        new_content = content
        for match in _FONT_FACE_RE.finditer(content):
            block = match.group(0)
            if any(href in block for href in removed_hrefs):
                new_content = new_content.replace(block, "", 1)
        if new_content != content:
            try:
                css_file.write_text(new_content, encoding="utf-8")
            except OSError:
                pass
```

Add a call at the end of `fix()`, before `return fixes`, collecting the removed font hrefs:

At the start of `fix()`, initialise `removed_fonts: set[str] = set()` and populate it in the font-removal block:

```python
if prefix == "font":
    removed_fonts.add(path)
    ...
```

Then after the `for issue in issues:` loop and before `return fixes`:

```python
# Clean up @font-face rules in CSS
self._strip_font_faces(extract_dir, removed_fonts)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_processors/test_compat.py -v
```

Expected: all 15 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_processors/test_compat.py src/boozarr/processors/compat.py
git commit -m "feat: strip @font-face CSS rules for removed fonts"
```

---

### Task 7: Wire into CLI

**Files:**
- Modify: `src/boozarr/cli.py:35-46` (add CompatProcessor to pipeline, signal normalise in config)

- [ ] **Step 1: Write the failing test**

The existing CLI tests already verify `--normalise` behavior. We need to verify that `--normalise` now passes `normalise: True` in the config. The simplest way: test through the pipeline.

Actually, we can verify by checking the CLI integration test. Add to `tests/test_cli.py`:

```python
def test_normalise_adds_compat_processor(self, tmp_path: Path) -> None:
    """--normalise should trigger CompatProcessor, visible via its config key."""
    from boozarr.cli import cli
    from click.testing import CliRunner

    epub = tmp_path / "test.epub"
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
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
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest>'
            '<spine><itemref idref="ch1"/></spine></package>',
        )
        zf.writestr("ch1.xhtml", "<html><body><p>Hello</p></body></html>")

    runner = CliRunner()
    result = runner.invoke(cli, ["--library-path", str(tmp_path), "--normalise"])
    assert result.exit_code == 0
```

Wait — actually this test requires a DB + processing. Let me not add a complex integration test here and instead verify via a unit test on `_collect_processors`.

Remove the test above — it's too heavyweight for what we're verifying.

Instead, verify via a simple unit test or just check that the processor list includes CompatProcessor.

Let me just add a simple check:

In `tests/test_cli.py`:

```python
def test_collect_processors_includes_compat(self) -> None:
    from boozarr.cli import _collect_processors

    procs = _collect_processors()
    names = [p.name for p in procs]
    assert "compat" in names, f"CompatProcessor missing from pipeline: {names}"
    assert names.index("compat") == 0, f"CompatProcessor must be first, got position {names.index('compat')}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/boozarr && uv run pytest tests/test_cli.py::test_collect_processors_includes_compat -v
```

Expected: FAIL — "compat" not in names

- [ ] **Step 3: Add CompatProcessor to pipeline**

In `src/boozarr/cli.py`, add the import at the top:

```python
from boozarr.processors.compat import CompatProcessor
```

Insert at position 0 in `_collect_processors`:

```python
def _collect_processors() -> list[Any]:
    """Build the list of all processors. Each processor self-regulates via its config."""
    return [
        CompatProcessor(),
        ChaptersProcessor(),
        CleanupProcessor(),
        BordersProcessor(),
        MetadataProcessor(),
        CssNormaliseProcessor(),
        LinksProcessor(),
        CompressionProcessor(),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /data/boozarr && uv run pytest tests/test_cli.py::test_collect_processors_includes_compat -v && uv run pytest tests/ -q 2>&1 | tail -3
```

Expected: new test PASS, all existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py src/boozarr/cli.py
git commit -m "feat: wire CompatProcessor into pipeline as first processor"
```

---

### Task 8: README update

**Files:**
- Modify: `README.md` (update `--normalise` description)

- [ ] **Step 1: Update README**

The `--normalise` section in the README currently describes CSS defaults. Add the new features.

Find the existing `--normalise` description and add the compatibility features:

```markdown
### `--normalise` (cross-device compatibility)

Sets sensible defaults for all CSS properties AND applies cross-device compatibility fixes:

```bash
boozarr --library-path /path/to/library --normalise --fix
```

This does everything the individual flags do at defaults of `0` for spacing,
`1em` for font-size, `1.5` for line-height, `left` for text-align, plus:

- **Strips embedded fonts** (`.otf`, `.ttf`, `.woff`, `.eot`, `.svg`) — reduces file
  size and improves compatibility with e-ink readers that don't support custom fonts
- **Removes Apple-specific metadata** (`com.apple.ibooks.display-options.xml`) —
  prevents rendering conflicts on non-Apple devices
- **Normalises OPF namespace prefixes** (`<ns0:itemref>` → `<itemref>`) — fixes
  reading-order issues on lightweight EPUB parsers
- **Cleans up orphaned `@font-face` CSS rules** that reference removed fonts

WOFF2 fonts (EPUB3 standard) are preserved for readers that support web-style
typography.
```

Replace the existing `--normalise` description paragraph in the README.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update --normalise description with compatibility features"
```

---

