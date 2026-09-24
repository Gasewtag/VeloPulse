"""Logging configuration with structured ISO timestamps."""

import logging
import sys


def setup_logging(debug: bool = False) -> None:
    """Configure standardized logging format with timestamps across all handlers."""
    log_level = logging.DEBUG if debug else logging.INFO
    log_format = "%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s]: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

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
