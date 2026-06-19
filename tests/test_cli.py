"""Tests for the boozarr CLI entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

from click.testing import CliRunner

from boozarr.cli import cli

if TYPE_CHECKING:
    from pathlib import Path


class TestCliBasic:
    def test_help_succeeds(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "boozarr" in result.output.lower()

    def test_version_succeeds(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0

    def test_requires_library_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code != 0
        assert "--library-path" in result.output

    def test_dry_run_on_empty_directory(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--library-path", str(tmp_path)])
        assert result.exit_code == 0

    def test_dry_run_with_epub(self, tmp_path: Path) -> None:
        runner = CliRunner()
        lib = tmp_path / "lib"
        lib.mkdir()
        epub = lib / "book.epub"
        epub.write_bytes(b"dummy epub")
        result = runner.invoke(cli, ["--library-path", str(lib)])
        assert result.exit_code == 0
