"""Redação de dados sensíveis antes de persistir logs."""

import logging

from core.logger import RedactingFormatter, SensitiveDataFilter, redact_sensitive


def test_redacts_email_phone_and_secrets():
    raw = (
        "para alice@example.com no +55 (11) 99999-1234 "
        "api_key=abc123 password segredo"
    )
    result = redact_sensitive(raw)

    assert "alice@example.com" not in result
    assert "+55 (11) 99999-1234" not in result
    assert "abc123" not in result
    assert "segredo" not in result
    assert "a***@example.com" in result
    assert "[PHONE_REDACTED]" in result
    assert result.count("[SECRET_REDACTED]") == 2


def test_filter_redacts_formatted_logging_arguments():
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "token=%s para %s", ("secret", "a@x.com"), None
    )

    assert SensitiveDataFilter().filter(record) is True
    assert "secret" not in record.getMessage()
    assert "a@x.com" not in record.getMessage()


def test_formatter_redacts_exception_text():
    try:
        raise RuntimeError("password=hunter2")
    except RuntimeError:
        record = logging.LogRecord(
            "test", logging.ERROR, __file__, 1, "falhou", (), __import__("sys").exc_info()
        )

    output = RedactingFormatter("%(message)s").format(record)
    assert "hunter2" not in output
    assert "[SECRET_REDACTED]" in output
