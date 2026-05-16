"""
utils/logger.py
----------------
Centralized logging setup for ClickBit.
All modules should import get_logger(__name__) from here.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

# Log file lives next to the project root
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "clickbit.log")

# Global flag to avoid adding handlers multiple times
_configured = False


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger with both console and rotating-file handlers.
    Safe to call multiple times; handlers are only attached once.
    """
    global _configured

    logger = logging.getLogger(name)

    if not _configured:
        logger.setLevel(logging.DEBUG)

        # ── Console handler ──────────────────────────────────────────────
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s – %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler.setFormatter(console_fmt)

        # ── Rotating file handler (max 2 MB, 3 backups) ──────────────────
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_fmt)

        # Attach to root logger so all child loggers inherit
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        root.addHandler(console_handler)
        root.addHandler(file_handler)

        _configured = True

    return logger
