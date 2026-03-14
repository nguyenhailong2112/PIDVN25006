# Shared logging configuration for PIDVN25006
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
import os
from typing import Optional

from core.path_utils import user_config_dir

_CONFIGURED = False


def _build_handlers(log_file: str):
    file_handler = TimedRotatingFileHandler(
        log_file, when="D", interval=1, backupCount=10, encoding="utf-8", delay=True
    )
    console_handler = logging.StreamHandler()
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(fmt)
    console_handler.setFormatter(fmt)
    return file_handler, console_handler


def _configure_root_if_needed(default_level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = os.getenv("PIDVN_LOG_DIR", str(user_config_dir() / "logs"))
    os.makedirs(log_dir, exist_ok=True)
    log_name = os.getenv("PIDVN_LOG_NAME", "app.log")
    log_file = os.path.join(log_dir, log_name)

    root = logging.getLogger()
    root.setLevel(default_level)

    existing_types = tuple(h.__class__ for h in root.handlers)
    file_h, console_h = _build_handlers(log_file)

    if TimedRotatingFileHandler not in existing_types:
        root.addHandler(file_h)
    if logging.StreamHandler not in existing_types:
        root.addHandler(console_h)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    _configure_root_if_needed()
    return logging.getLogger(name if name else __name__)


def set_log_level(level: str | int) -> None:
    _configure_root_if_needed()
    root = logging.getLogger()
    if isinstance(level, str):
        level = level.upper()
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARN": logging.WARNING,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        root.setLevel(level_map.get(level, logging.INFO))
    else:
        root.setLevel(level)
