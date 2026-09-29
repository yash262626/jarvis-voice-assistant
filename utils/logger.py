"""Rotating file + console logging with optional redaction of dictated text.

Business text (customer names, GST numbers, order numbers) is *not* written to
the log unless ``log_typed_text`` is explicitly turned on in config.json.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import time
from pathlib import Path
from typing import Optional

from utils.config import Config, project_root

_CONFIGURED = False
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _SafeStreamHandler(logging.StreamHandler):
    """Console handler that survives a missing/!UTF-8 stdout (pythonw.exe, exe)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.stream is None:
                return
            super().emit(record)
        except Exception:                                       # noqa: BLE001
            pass


def setup_logging(config: Optional[Config] = None) -> logging.Logger:
    """Configure the root logger once. Safe to call multiple times."""
    global _CONFIGURED
    root = logging.getLogger()
    if _CONFIGURED:
        return root

    level_name = (config.get("log_level") if config else "INFO") or "INFO"
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    root.setLevel(level)

    log_dir = project_root() / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "jarvis.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        root.addHandler(file_handler)
    except OSError:
        pass  # read-only install directory: console logging still works

    console = _SafeStreamHandler(stream=sys.stdout)
    console.setFormatter(logging.Formatter("%(levelname)-7s %(name)-18s %(message)s"))
    root.addHandler(console)

    logging.getLogger("comtypes").setLevel(logging.WARNING)
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    logging.getLogger("openwakeword").setLevel(logging.WARNING)

    _CONFIGURED = True
    root.debug("Logging initialised at %s", level_name)
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def redact(text: str, allow: bool = False, keep: int = 12) -> str:
    """Return text for logging - shortened unless ``allow`` is True."""
    if text is None:
        return ""
    if allow:
        return text
    text = str(text)
    if len(text) <= keep:
        return text
    return f"{text[:keep]}...<{len(text)} chars>"


def prune_old_logs(days: int = 14) -> None:
    """Delete rotated logs older than ``days``. Best effort, never raises."""
    log_dir = project_root() / "logs"
    cutoff = time.time() - days * 86400
    try:
        for item in log_dir.glob("jarvis.log.*"):
            if item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
    except OSError:
        pass
