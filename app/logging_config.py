"""Centralised logging configuration for the application.

Call ``configure_logging`` once at startup (before the FastAPI app is created)
to set JSON-formatted structured log output for all loggers, including Uvicorn.
"""

from __future__ import annotations

import logging
import logging.config


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure logging for the entire process.

    Sets up a single console handler and applies it as the root handler so
    every ``logging.getLogger(__name__)`` call in the codebase inherits it
    automatically.  Uvicorn's access and error loggers are also reconfigured
    so their output is consistent.

    :param log_level: Minimum log level for the root logger (default ``"INFO"``).
                      Override via the ``LOG_LEVEL`` environment variable.
    :param log_format: Output format — ``"json"`` (default, machine-readable,
                       suitable for log aggregation) or ``"text"`` (human-readable
                       coloured lines, convenient for local development).
                       Override via the ``LOG_FORMAT`` environment variable.
    """
    if log_format == "text":
        formatter: dict = {
            "format": "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
            "datefmt": "%H:%M:%S",
        }
    else:
        formatter = {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }

    LOGGING_CONFIG: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": formatter,
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "console",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["console"],
        },
        "loggers": {
            "uvicorn": {"handlers": ["console"], "level": log_level, "propagate": False},
            "uvicorn.access": {"handlers": ["console"], "level": log_level, "propagate": False},
            "uvicorn.error": {"handlers": ["console"], "level": log_level, "propagate": False},
        },
    }
    logging.config.dictConfig(LOGGING_CONFIG)
