# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Configure logging for GitHub runner image builder."""

import logging
import logging.handlers
import pathlib

LOG_FILE_DIR = pathlib.Path.home() / "github-runner-image-builder/log"
LOG_FILE_PATH = LOG_FILE_DIR / "info.log"
ERROR_LOG_FILE_PATH = LOG_FILE_DIR / "error.log"


def configure(log_level: str | int):
    """Configure the global log configurations."""
    LOG_FILE_DIR.mkdir(parents=True, exist_ok=True)
    log_handler = logging.handlers.WatchedFileHandler(filename=LOG_FILE_PATH, encoding="utf-8")
    log_handler.setLevel(log_level.capitalize() if isinstance(log_level, str) else log_level)
    error_log_handler = logging.handlers.WatchedFileHandler(
        filename=ERROR_LOG_FILE_PATH, encoding="utf-8"
    )
    logging.basicConfig(
        level=log_level,
        handlers=(log_handler, error_log_handler),
        encoding="utf-8",
    )
