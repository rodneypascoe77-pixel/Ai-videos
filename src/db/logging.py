"""Dual-sink structured logger: console + the pipeline_logs table.

Every module gets a logger via get_logger(__name__-ish). Info/warning/error rows
are persisted so the dashboard (later phase) can read them; debug is console-only.

    from db.logging import get_logger
    log = get_logger("sources.youtube")
    log.info("fetched videos", count=42)
"""

from __future__ import annotations

import logging
from typing import Any

from db.models import LogLevel, PipelineLog
from db.session import session_scope

_console_configured: set[str] = set()


class PipelineLogger:
    def __init__(self, module: str) -> None:
        self.module = module
        if module not in _console_configured:
            logger = logging.getLogger(module)
            if not logger.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(
                    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
                )
                logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            _console_configured.add(module)
        self._console = logging.getLogger(module)

    def _persist(self, level: LogLevel, message: str, context: dict | None) -> None:
        try:
            with session_scope() as session:
                session.add(
                    PipelineLog(
                        module=self.module,
                        level=level,
                        message=message,
                        context_json=context or None,
                    )
                )
        except Exception:
            # Logging must never crash the pipeline.
            self._console.warning("Failed to persist log row", exc_info=False)

    def debug(self, message: str, **context: Any) -> None:
        self._console.debug(message)  # console-only, not persisted

    def info(self, message: str, **context: Any) -> None:
        self._console.info(message)
        self._persist(LogLevel.info, message, context)

    def warning(self, message: str, **context: Any) -> None:
        self._console.warning(message)
        self._persist(LogLevel.warning, message, context)

    def error(self, message: str, **context: Any) -> None:
        self._console.error(message)
        self._persist(LogLevel.error, message, context)


def get_logger(module: str) -> PipelineLogger:
    return PipelineLogger(module)
