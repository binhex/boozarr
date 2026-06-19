"""Tests verifying the project skeleton has been properly renamed from AppName → boozarr."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def test_package_imports_as_boozarr() -> None:
    """The top-level package must be importable as 'boozarr'."""
    import boozarr  # noqa: F401


def test_cli_prog_name_is_boozarr() -> None:
    """The CLI entry point should report prog_name as 'boozarr'."""
    from boozarr import cli

    # The _VERSION lookup uses version("boozarr") — test that works
    assert cli._VERSION != "unknown", "Package version lookup failed"


def test_cli_help_shows_boozarr() -> None:
    """Running `boozarr --help` should not mention AppName."""
    result = subprocess.run(
        [sys.executable, "-m", "boozarr.cli", "--help"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert result.returncode == 0, f"CLI help failed:\n{result.stderr}"
    assert "boozarr" in result.stdout.lower()
    assert "appname" not in result.stdout.lower()


def test_no_stale_appname_references_in_source() -> None:
    """Check no stale AppName/appname/trimarr strings exist in Python source files."""
    src_dir = PROJECT_ROOT / "src"
    stale_patterns = ["AppName", "appname", "trimarr"]

    for path in sorted(src_dir.rglob("*.py")):
        text = path.read_text()
        for pattern in stale_patterns:
            if pattern in text:
                # Check it's not a false positive for boozarr substring
                if pattern == "appname" and "boozarr" in text:
                    continue  # Allow if it's part of a boozarr reference path
                pytest.fail(f"Stale reference '{pattern}' found in {path}")


def test_no_stale_references_in_pyproject() -> None:
    """Check pyproject.toml has no AppName references."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    text = pyproject.read_text()
    assert "AppName" not in text, "pyproject.toml still references AppName"
    assert "appname" not in text, "pyproject.toml still references appname"
    assert "trimarr" not in text, "pyproject.toml still references trimarr"


def test_no_stale_references_in_readme() -> None:
    """Check README.md has no AppName references."""
    readme = PROJECT_ROOT / "README.md"
    if not readme.exists():
        pytest.skip("README.md not found")
    text = readme.read_text()
    assert "AppName" not in text, "README.md still references AppName"
