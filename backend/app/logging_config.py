"""Structured logging.

One place configures the format so every module's logs carry the same fields
(timestamp, level, logger, message) and options.  Credentials are never logged:
the config values themselves are not interpolated into log lines anywhere.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in ("provider", "event_id", "article_id", "duration_ms", "count"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return (
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} "
            f"{record.levelname:<7} {record.name}: {record.getMessage()}"
        )


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_logs else ConsoleFormatter())

    root.addHandler(handler)
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    # Third-party noise at INFO drowns useful signal.
    for noisy in ("httpx", "httpcore", "urllib3", "watchfiles", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
