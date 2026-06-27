"""Command-line interface for boozarr."""

from __future__ import annotations

import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import click

from boozarr.db import ProcessingDB
from boozarr.logger import create_logger
from boozarr.pipeline import Pipeline
from boozarr.processors.borders import BordersProcessor
from boozarr.processors.chapters import ChaptersProcessor
from boozarr.processors.cleanup import CleanupProcessor
from boozarr.processors.compression import CompressionProcessor
from boozarr.processors.css_normalise import CssNormaliseProcessor
from boozarr.processors.links import LinksProcessor
from boozarr.processors.metadata import MetadataProcessor
from boozarr.report import Report
from boozarr.utils import get_project_root

try:
    _VERSION = version("boozarr")
except PackageNotFoundError:
    _VERSION = "unknown"

_PROJECT_ROOT = get_project_root()
_DEFAULT_DB_PATH = f"{_PROJECT_ROOT}/db/boozarr.db"
_DEFAULT_LOGS_PATH = f"{_PROJECT_ROOT}/logs/boozarr.log"


def _collect_processors() -> list[Any]:
    """Build the list of all processors. Each processor self-regulates via its config."""
    return [
        ChaptersProcessor(),
        CleanupProcessor(),
        BordersProcessor(),
        MetadataProcessor(),
        CssNormaliseProcessor(),
        LinksProcessor(),
        CompressionProcessor(),
    ]


@click.command(context_settings={"show_default": True})
@click.option(
    "--library-path",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    metavar="<DIR>",
    help="Directory containing EPUB files.",
)
@click.option("--fix", is_flag=True, default=False, help="Apply fixes (default: dry-run).")
@click.option(
    "--no-backup", is_flag=True, default=False, help="Disable automatic .bak backup copies (backups are on by default)."
)
@click.option(
    "--db-path",
    default=_DEFAULT_DB_PATH,
    type=click.Path(file_okay=True, dir_okay=False, resolve_path=True),
    metavar="<path>",
    help="SQLite DB path.",
)
@click.option(
    "--log-path",
    default=_DEFAULT_LOGS_PATH,
    type=click.Path(file_okay=True, dir_okay=False, resolve_path=True),
    metavar="<path>",
    help="Log file path.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    metavar="<level>",
    help="Logging level.",
)
@click.option(
    "--normalise",
    is_flag=True,
    help="Apply all CSS defaults (--margin --padding --font-size --line-height --border --text-align --text-indent).",
)
@click.option("--cleanup", is_flag=True, help="Remove empty <p>, <div>, <span> elements from XHTML.")
@click.option(
    "--text-align",
    type=click.Choice(["left", "center", "right", "justify"], case_sensitive=False),
    default=None,
    is_flag=False,
    flag_value="left",
    metavar="<left|center|right|justify>",
    help="Target text-align (no value = left).",
)
@click.option(
    "--border",
    type=int,
    default=None,
    is_flag=False,
    flag_value=0,
    metavar="<int>",
    help="Target border, px (no value = 0).",
)
@click.option(
    "--margin",
    type=int,
    default=None,
    is_flag=False,
    flag_value=2,
    metavar="<int>",
    help="Target margin, px (no value = 2).",
)
@click.option(
    "--padding",
    type=int,
    default=None,
    is_flag=False,
    flag_value=2,
    metavar="<int>",
    help="Target padding, px (no value = 2).",
)
@click.option(
    "--font-size",
    type=int,
    default=None,
    is_flag=False,
    flag_value=14,
    metavar="<int>",
    help="Target font size, px (no value = 14).",
)
@click.option(
    "--line-height",
    type=float,
    default=None,
    is_flag=False,
    flag_value=1.2,
    metavar="<float>",
    help="Target line height (no value = 1.2).",
)
@click.option(
    "--text-indent",
    type=int,
    default=None,
    is_flag=False,
    flag_value=0,
    metavar="<int>",
    help="Target text indent, px (no value = 0).",
)
@click.option("--check-external-links", is_flag=True, help="Validate external URLs.")
@click.option("--compress", type=int, default=None, metavar="<int>", help="Apply EPUB recompression (0=store, 9=best).")
@click.version_option(version=_VERSION, prog_name="boozarr")
def cli(
    library_path: str,
    fix: bool,
    no_backup: bool,
    db_path: str,
    log_path: str,
    log_level: str,
    border: int | None,
    margin: int | None,
    padding: int | None,
    font_size: int | None,
    line_height: float | None,
    text_indent: int | None,
    text_align: str | None,
    check_external_links: bool,
    compress: int | None,
    normalise: bool,
    cleanup: bool,
) -> None:
    """Boozarr - Automated EPUB Editor.

    Batch-process EPUB files: run checks and fixes for chapters, borders,
    metadata, CSS, links, and compression across an entire library.
    """
    logger = create_logger(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        log_level,
        log_path,
    )

    db = ProcessingDB(Path(db_path))

    processors = _collect_processors()

    if normalise:
        if border is None:
            border = 0
        if margin is None:
            margin = 2
        if padding is None:
            padding = 2
        if font_size is None:
            font_size = 14
        if line_height is None:
            line_height = 1.2
        if text_align is None:
            text_align = "left"
        if text_indent is None:
            text_indent = 0

    config = {
        "border": border,
        "margin": margin,
        "padding": padding,
        "font_size": font_size,
        "line_height": line_height,
        "text_align": text_align,
        "text_indent": text_indent,
        "check_external_links": check_external_links,
        "compress": compress,
        "cleanup": cleanup,
    }

    pipeline = Pipeline(db=db, processors=processors, config=config, fix=fix, backup=not no_backup)
    report = Report()

    lib_path = Path(library_path)
    epub_files = sorted(lib_path.rglob("*.epub"))

    if not epub_files:
        logger.warning("No .epub files found in {}", library_path)
        return

    logger.info("Found {} EPUB files in {}", len(epub_files), library_path)

    start = time.monotonic()
    for epub_file in epub_files:
        result = pipeline.process_epub(epub_file)
        line = report.log_line(
            result["file_path"],
            result["status"],
            issues=result["issues"],
            fixes=result["fixes"],
            fix_details=result.get("fix_details"),
            dry_run=result.get("dry_run", False),
        )
        logger.info(line)

    elapsed = time.monotonic() - start
    summary = report.final_summary(duration_s=elapsed)
    logger.info("Summary:\n{}", summary)
    db.close()


if __name__ == "__main__":
    cli()
