"""Structured logging with secret redaction."""

import logging
import re
import sys

import structlog

SECRET_KEYS = re.compile(r"(password|secret|token|api[_-]?key|authorization|cookie|csrf)", re.I)


def _redact(_, __, event_dict):
    for key in list(event_dict.keys()):
        if SECRET_KEYS.search(key):
            event_dict[key] = "[redacted]"
    return event_dict


def setup_logging(level: str = "INFO", as_json: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    renderer = structlog.processors.JSONRenderer() if as_json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()
