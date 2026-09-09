import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.request_context import get_request_id

_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)"
        r"(access_token|refresh_token|client_secret|"
        r"password|authorization_code|code_verifier)"
        r"\s*[:=]\s*[^\s,;]+"
    ),
)


_ALLOWED_EXTRA_FIELDS = {
    "event",
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "provider",
    "error_code",
}


def redact_sensitive_value(
    value: Any,
) -> Any:
    if not isinstance(value, str):
        return value

    sanitized = value

    sanitized = _SENSITIVE_PATTERNS[0].sub(
        "Bearer [REDACTED]",
        sanitized,
    )

    sanitized = _SENSITIVE_PATTERNS[1].sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        sanitized,
    )

    return sanitized


class CredentialSafeJsonFormatter(logging.Formatter):
    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_value(record.getMessage()),
        }

        request_id = getattr(
            record,
            "request_id",
            None,
        )

        if not request_id:
            request_id = get_request_id()

        if request_id != "unknown":
            payload["request_id"] = redact_sensitive_value(request_id)

        for field in _ALLOWED_EXTRA_FIELDS:
            if field == "request_id":
                continue

            if hasattr(record, field):
                value = getattr(
                    record,
                    field,
                )

                payload[field] = redact_sensitive_value(value)

        if record.exc_info:
            exception = record.exc_info[1]

            payload["exception_type"] = (
                type(exception).__name__ if exception else "UnknownException"
            )

            if exception:
                payload["exception_message"] = redact_sensitive_value(str(exception))

        return json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )


def configure_logging(
    log_level: str = "INFO",
) -> None:
    level = getattr(
        logging,
        log_level.upper(),
        logging.INFO,
    )

    handler = logging.StreamHandler(sys.stdout)

    handler.setFormatter(CredentialSafeJsonFormatter())

    root_logger = logging.getLogger()

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # We emit our own HTTP request logs.
    # Avoid duplicate Uvicorn access logs.
    logging.getLogger("uvicorn.access").disabled = True

    for logger_name in (
        "uvicorn",
        "uvicorn.error",
        "fastapi",
    ):
        logger = logging.getLogger(logger_name)

        logger.handlers.clear()
        logger.propagate = True
