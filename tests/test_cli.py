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

    def test_no_skip_flags_in_help(self) -> None:
        """Skip flags (--skip-*, --no-compress) must not appear in --help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        skip_flags = [
            "--skip-chapters",
            "--skip-borders",
            "--skip-metadata",
            "--skip-css",
            "--skip-links",
            "--no-compress",
        ]
        for flag in skip_flags:
            assert flag not in result.output, f"{flag} should not be in --help output"

    def test_compress_flag_in_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "--compress" in result.output
