import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Context variable for request correlation ID across async tasks
request_id_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="system"
)


class JSONFormatter(logging.Formatter):
    """
    Format logs as JSON objects adhering to production observability standards.
    Never logs passwords, tokens, or raw secrets.
    """

    SENSITIVE_KEYS = {
        "password",
        "token",
        "secret",
        "authorization",
        "hashed_password",
        "access_token",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx_var.get(),
            "environment": getattr(record, "environment", "unknown"),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields if provided, redacting sensitive keys
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            for key, val in record.extra.items():
                if any(sens in key.lower() for sens in self.SENSITIVE_KEYS):
                    log_data[key] = "[REDACTED]"
                else:
                    log_data[key] = val

        return json.dumps(log_data)


def setup_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Configures root logger with appropriate formatter and level."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if log_format.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] [ReqID: %(request_id)s] %(message)s",
                defaults={"request_id": "system"},
            )
        )

    root_logger.addHandler(handler)

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
