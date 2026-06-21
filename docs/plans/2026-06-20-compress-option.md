# `--compress` CLI Option Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--compress` CLI option that activates EPUB recompression only when specified.

**Architecture:** Follows the existing "auto-activate when configured" pattern. `CompressionProcessor.check()` returns `[]` when `config.get("compress")` is `None`. `fix()` sets `epub._compress_level` on the wrapper. `Pipeline` already calls `wrapper.repack()` which reads `_compress_level` and passes it to `ZipFile`.

**Tech Stack:** Python 3.12, Click, zipfile, pytest

---

### Task 1: CompressionProcessor — config-gated check() + fix()

**Files:**
- Modify: `src/boozarr/processors/compression.py:13-30`
- Modify: `tests/test_processors/test_compression.py`

- [ ] **Step 1: Write failing tests**

```python
class TestCompressionCheck:
    def test_no_issues_when_clean(self) -> None:
        epub = MagicMock()
        epub.extra_files = [Path("OEBPS/content.opf")]
        assert CompressionProcessor().check(epub) == []

    def test_no_issues_when_compress_not_configured(self) -> None:
        """When config has no 'compress' key (or None), check returns nothing."""
        epub = MagicMock()
        epub.extra_files = [Path(".DS_Store"), Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub, {})
        assert issues == []

    def test_issues_when_compress_configured(self) -> None:
        """When config has 'compress' set, check reports extraneous files."""
        epub = MagicMock()
        epub.extra_files = [Path(".DS_Store"), Path("OEBPS/content.opf")]
        issues = CompressionProcessor().check(epub, {"compress": 9})
        assert len(issues) == 1


class TestCompressionFix:
    def test_fix_cleans_extraneous(self) -> None:
        epub = MagicMock()
        issue = MagicMock(
            location="archive root",
            description="Found 1 extraneous file(s)",
        )
        fixes = CompressionProcessor().fix(epub, [issue], {"compress": 9})
        assert len(fixes) == 1
        assert "cleaned" in fixes[0].new_value

    def test_fix_sets_compress_level(self) -> None:
        """fix() should set epub._compress_level to the configured value."""
        epub = MagicMock()
        CompressionProcessor().fix(epub, [], {"compress": 7})
        assert epub._compress_level == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_processors/test_compression.py -v --no-cov`
Expected: FAIL — `test_no_issues_when_compress_not_configured` still reports issues, `test_fix_sets_compress_level` fails with AttributeError.

- [ ] **Step 3: Implement — gate check() on config, set _compress_level in fix()**

```python
def check(self, epub: Any, config: dict[str, Any] | None = None) -> list[Issue]:
    if config is None or config.get("compress") is None:
        return []
    issues: list[Issue] = []
    extra = [f for f in getattr(epub, "extra_files", []) if f.name in _EXTRA]
    if extra:
        issues.append(
            Issue(
                processor=self.name,
                severity="info",
                location="archive root",
                description=f"Found {len(extra)} extraneous file(s): {[e.name for e in extra]}",
                fix_possible=True,
            )
        )
    return issues

def fix(self, epub: Any, issues: list[Issue], config: dict[str, Any]) -> list[Fix]:
    epub._compress_level = config.get("compress")
    return [
        Fix(
            processor=self.name,
            location=i.location,
            description="Stripped extraneous files",
            old_value=i.description,
            new_value="cleaned",
        )
        for i in issues
    ]
```

- [ ] **Step 4: Run tests to verify GREEN**

Run: `pytest tests/test_processors/test_compression.py -v --no-cov`
Expected: 5 passed.

- [ ] **Step 5: Verify full suite still passes**

Run: `pytest --no-cov -q`
Expected: 111 passed.

---

### Task 2: EpubWrapper.repack() — use _compress_level

**Files:**
- Modify: `src/boozarr/epub.py:85-91`

- [ ] **Step 1: Implement**

```python
def repack(self, output_path: Path) -> None:
    """Re-zip the extracted directory into *output_path* with deflate compression."""
    if self._extract_dir is None or not self._extract_dir.exists():
        raise RuntimeError("No extracted directory to repack. Call extract() first.")
    compresslevel = getattr(self, "_compress_level", None)
    with zipfile.ZipFile(
        output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=compresslevel
    ) as zf:
        for fpath in sorted(self._extract_dir.rglob("*")):
            if fpath.is_file():
                zf.write(fpath, str(fpath.relative_to(self._extract_dir)))
```

- [ ] **Step 2: Verify tests**

Run: `pytest --no-cov -q`
Expected: 111 passed.

---

### Task 3: CLI — add `--compress` option

**Files:**
- Modify: `src/boozarr/cli.py` (add decorator, param, config key)

- [ ] **Step 1: Add Click option**

Insert after `--no-backup` option block (around line 68):

```python
@click.option(
    "--compress",
    type=int,
    default=None,
    metavar="<0-9>",
    help="Apply EPUB recompression (0=store, 9=best).",
)
```

- [ ] **Step 2: Add parameter to `cli()` signature**

Insert `compress: int | None,` into the `cli()` parameter list (after `check_external_links`):

```python
def cli(
    library_path: str,
    fix: bool,
    no_backup: bool,
    db_path: str,
    log_path: str,
    log_level: str,
    border: str | None,
    margin: str | None,
    padding: str | None,
    font_size: str | None,
    line_height: str | None,
    text_align: str | None,
    check_external_links: bool,
    compress: int | None,
) -> None:
```

- [ ] **Step 3: Add to config dict**

In the `config = {...}` block, add:

```python
    config = {
        "border": border,
        "margin": margin,
        "padding": padding,
        "font_size": font_size,
        "line_height": line_height,
        "text_align": text_align,
        "check_external_links": check_external_links,
        "compress": compress,
    }
```

- [ ] **Step 4: Add CLI test**

In `tests/test_cli.py`, add:

```python
    def test_compress_flag_in_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "--compress" in result.output
```

- [ ] **Step 5: Verify full suite**

Run: `pytest --no-cov -q`
Expected: 112 passed.

---

### Task 4: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add `--compress` to options table**

Insert a row in the options table after `--check-external-links`:

```
| `--compress` | — | Apply EPUB recompression level (0=store, 9=best, only when specified) |
```

- [ ] **Step 2: Verify no markdown lint issues**

Run: `markdownlint README.md 2>/dev/null || echo "no markdownlint available"`
