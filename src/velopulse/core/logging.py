"""Logging configuration with structured ISO timestamps, JSON format, and correlation tracing."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from velopulse.observability.context import get_correlation_id


class StructuredJSONFormatter(logging.Formatter):
    """Formats log records as newline-delimited JSON objects with correlation IDs."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        cid = get_correlation_id()
        if cid:
            log_entry["correlation_id"] = cid

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_entry, default=str)


class TextCorrelationFormatter(logging.Formatter):
    """Formats log records with ISO timestamps and active correlation ID in text format."""

    def format(self, record: logging.LogRecord) -> str:
        cid = get_correlation_id()
        record.correlation_prefix = f"[{cid}]" if cid else "[-]"
        return super().format(record)


def setup_logging(debug: bool = False, log_format: str = "auto") -> None:
    """Configure standardized logging format with correlation IDs across all handlers."""
    log_level = logging.DEBUG if debug else logging.INFO

    use_json = log_format == "json"

    formatter: logging.Formatter
    if use_json:
        formatter = StructuredJSONFormatter()
    else:
        text_format = (
            "%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] %(correlation_prefix)s: %(message)s"
        )
        date_format = "%Y-%m-%d %H:%M:%S"
        formatter = TextCorrelationFormatter(fmt=text_format, datefmt=date_format)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)

    # Ensure uvicorn access and error loggers include timestamp formatting
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        uvicorn_logger.addHandler(handler)
        uvicorn_logger.propagate = False

    # Quiet noisy internal 3rd-party connection/handshake debug messages
    logging.getLogger("redis").setLevel(logging.INFO)
    logging.getLogger("asyncpg").setLevel(logging.INFO)
