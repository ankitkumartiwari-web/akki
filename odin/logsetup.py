from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import database_path


def log_path() -> Path:
    return database_path().parent / "odin.log"


def configure_logging(path: Path | str | None = None, level: int = logging.INFO) -> Path:
    logger = logging.getLogger("odin")
    target = Path(path) if path is not None else log_path()
    existing = getattr(logger, "_odin_handler", None)
    if isinstance(existing, RotatingFileHandler):
        return Path(existing.baseFilename)
    target.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        target,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.setLevel(level)
    logger.propagate = False
    logger.addHandler(handler)
    setattr(logger, "_odin_handler", handler)
    return target
