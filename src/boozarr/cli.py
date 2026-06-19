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


def _collect_processors(
    skip_chapters: bool,
    skip_borders: bool,
    skip_metadata: bool,
    skip_css: bool,
    skip_links: bool,
    no_compress: bool,
) -> list[Any]:
    """Build the list of enabled processors based on skip flags."""
    enabled: list[Any] = []
    if not skip_chapters:
        enabled.append(ChaptersProcessor())
    if not skip_borders:
        enabled.append(BordersProcessor())
    if not skip_metadata:
        enabled.append(MetadataProcessor())
    if not skip_css:
        enabled.append(CssNormaliseProcessor())
    if not skip_links:
        enabled.append(LinksProcessor())
    if not no_compress:
        enabled.append(CompressionProcessor())
    return enabled


@click.command(context_settings={"show_default": True})
@click.option(
    "--library-path",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    metavar="<DIR>",
    help="Directory containing EPUB files.",
)
@click.option("--fix", is_flag=True, default=False, help="Apply fixes (default: dry-run).")
@click.option("--backup", is_flag=True, default=False, help="Create .bak copies before modifying.")
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
@click.option("--skip-chapters", is_flag=True, help="Skip chapter detection.")
@click.option("--skip-borders", is_flag=True, help="Skip border normalisation.")
@click.option("--skip-metadata", is_flag=True, help="Skip metadata fixer.")
@click.option("--skip-css", is_flag=True, help="Skip CSS normalisation.")
@click.option("--skip-links", is_flag=True, help="Skip link checker.")
@click.option("--no-compress", is_flag=True, help="Skip compression.")
@click.option("--border", default="none", metavar="<val>", help="Target border.")
@click.option("--margin", default="1em", metavar="<val>", help="Target margin.")
@click.option("--padding", default="0", metavar="<val>", help="Target padding.")
@click.option("--font-size", default="1em", metavar="<val>", help="Target font size.")
@click.option("--line-height", default="1.5", metavar="<val>", help="Target line height.")
@click.option("--paragraph-spacing", default="1em", metavar="<val>", help="Target paragraph spacing.")
@click.option("--check-external-links", is_flag=True, help="Validate external URLs.")
@click.version_option(version=_VERSION, prog_name="boozarr")
def cli(
    library_path: str,
    fix: bool,
    backup: bool,
    db_path: str,
    log_path: str,
    log_level: str,
    skip_chapters: bool,
    skip_borders: bool,
    skip_metadata: bool,
    skip_css: bool,
    skip_links: bool,
    no_compress: bool,
    border: str,
    margin: str,
    padding: str,
    font_size: str,
    line_height: str,
    paragraph_spacing: str,
    check_external_links: bool,
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

    processors = _collect_processors(
        skip_chapters,
        skip_borders,
        skip_metadata,
        skip_css,
        skip_links,
        no_compress,
    )

    config = {
        "border": border,
        "margin": margin,
        "padding": padding,
        "font_size": font_size,
        "line_height": line_height,
        "paragraph_spacing": paragraph_spacing,
        "check_external_links": check_external_links,
    }

    pipeline = Pipeline(db=db, processors=processors, config=config, fix=fix, backup=backup)
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
        )
        logger.info(line)

    elapsed = time.monotonic() - start
    summary = report.final_summary(duration_s=elapsed)
    logger.info("Summary:\n{}", summary)
    db.close()


if __name__ == "__main__":
    cli()
