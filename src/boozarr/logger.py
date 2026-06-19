"""Logging utilities for boozarr."""

from __future__ import annotations

import os
import sys
from contextlib import suppress

import loguru
from loguru import logger as _logger


def create_logger(log_format: str, log_level: str = "INFO", log_path: str | None = None) -> loguru.Logger:
    """Return a configured Loguru logger instance.

    Removes handler 0 (the default stderr handler) rather than calling
    ``remove()`` with no arguments so that handlers added by other
    modules are not silently destroyed.

    Args:
        log_format: Loguru format string applied to both console and file sinks.
        log_level: Minimum log level for both sinks.
        log_path: Optional path to a log file. The parent directory is created
            automatically if it does not already exist.
    """
    with suppress(ValueError):
        _logger.remove(0)  # remove only the default handler

    # Console sink
    _logger.add(
        sink=sys.stdout,
        level=log_level.upper(),
        format=log_format,
        colorize=True,
        backtrace=False,
        diagnose=False,
    )

    # File sink
    if log_path is not None:
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        _logger.add(
            sink=log_path,
            level=log_level.upper(),
            format=log_format,
            rotation="10 MB",
            retention=3,
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
        )

    return _logger
