"""Logging configuration utilities for the trading automation stack."""
from __future__ import annotations

import logging
import logging.config
from typing import Any, Dict, Optional

DEFAULT_LOGGING_CONFIG: Dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "INFO",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
}

_configured = False


def configure_logging(config: Optional[Dict[str, Any]] = None) -> None:
    """Apply the provided logging configuration.

    Parameters
    ----------
    config:
        Optional ``dict`` containing a logging configuration compatible with
        :func:`logging.config.dictConfig`. When ``None`` the module level
        :data:`DEFAULT_LOGGING_CONFIG` is used.
    """

    global _configured
    logging.config.dictConfig(config or DEFAULT_LOGGING_CONFIG)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger initialised with the repository wide configuration."""

    if not _configured:
        configure_logging()
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    **context: Any,
) -> None:
    """Log a structured event.

    ``context`` values are attached to the log record via the ``extra``
    dictionary so downstream handlers can serialise them (for example into
    JSON) if desired.  Consumers that are not interested in the structured
    payload simply display the base message.
    """

    logger.log(level, message, extra={"context": context} if context else None)
