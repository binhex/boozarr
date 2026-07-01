"""Tests for the boozarr CLI entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

from click.testing import CliRunner

from boozarr.cli import cli

if TYPE_CHECKING:
    from pathlib import Path


class TestCompatCliIntegration:
    def test_collect_processors_includes_compat(self) -> None:
        from boozarr.cli import _collect_processors

        procs = _collect_processors()
        names = [p.name for p in procs]
        assert "compat" in names, f"CompatProcessor missing from pipeline: {names}"
        assert names.index("compat") == 0


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

    def test_normalise_flag_sets_defaults(self, tmp_path: Path) -> None:
        """--normalise should set all CSS defaults without errors."""
        import zipfile

        lib = tmp_path / "lib"
        lib.mkdir()
        epub_path = lib / "book.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", "<package/>")
            zf.writestr("OEBPS/ch1.xhtml", "<p>Text</p>")

        db_path = tmp_path / "test.db"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--library-path",
                str(lib),
                "--normalise",
                "--db-path",
                str(db_path),
                "--log-path",
                str(tmp_path / "test.log"),
            ],
        )
        assert result.exit_code == 0, result.output
