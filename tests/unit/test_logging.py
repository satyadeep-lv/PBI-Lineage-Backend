import json
import logging

from app.core.logging import (
    CredentialSafeJsonFormatter,
)


def _format_message(
    message: str,
) -> dict:
    formatter = CredentialSafeJsonFormatter()

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)

    return json.loads(output)


def test_bearer_token_is_redacted():
    secret = "very-secret-token"

    payload = _format_message(f"Authorization: Bearer {secret}")

    serialized = json.dumps(payload)

    assert secret not in serialized
    assert "[REDACTED]" in serialized


def test_access_token_is_redacted():
    secret = "secret-access-token"

    payload = _format_message(f"access_token={secret}")

    serialized = json.dumps(payload)

    assert secret not in serialized
    assert "[REDACTED]" in serialized


def test_client_secret_is_redacted():
    secret = "my-client-secret"

    payload = _format_message(f"client_secret={secret}")

    serialized = json.dumps(payload)

    assert secret not in serialized
    assert "[REDACTED]" in serialized


def test_password_is_redacted():
    secret = "my-password"

    payload = _format_message(f"password={secret}")

    serialized = json.dumps(payload)

    assert secret not in serialized
    assert "[REDACTED]" in serialized
