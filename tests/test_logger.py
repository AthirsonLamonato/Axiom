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


def test_setup_logging_is_idempotent_and_accepts_plain_filename(tmp_path, monkeypatch):
    from core.config import Config
    from core.logger import setup_logging

    config = Config.__new__(Config)
    config.get = lambda key, default=None: {
        "logging.level": "INFO",
        "logging.file": str(tmp_path / "pacoca.log"),
        "logging.max_mb": 0,
    }.get(key, default)

    root = logging.getLogger()
    before = list(root.handlers)
    try:
        setup_logging(config)
        first = [h for h in root.handlers if getattr(h, "_pacoca_handler", False)]
        setup_logging(config)
        second = [h for h in root.handlers if getattr(h, "_pacoca_handler", False)]
        assert len(first) == 2
        assert len(second) == 2
        assert (tmp_path / "pacoca.log").exists()
    finally:
        for handler in list(root.handlers):
            if getattr(handler, "_pacoca_handler", False):
                root.removeHandler(handler)
                handler.close()
        for handler in before:
            if handler not in root.handlers:
                root.addHandler(handler)
        monkeypatch.undo()


def test_setup_logging_falls_back_for_invalid_max_mb(tmp_path):
    from core.config import Config
    from core.logger import setup_logging

    config = Config.__new__(Config)
    config.get = lambda key, default=None: {
        "logging.level": "INFO",
        "logging.file": str(tmp_path / "pacoca.log"),
        "logging.max_mb": "invalido",
    }.get(key, default)

    root = logging.getLogger()
    try:
        setup_logging(config)
        assert (tmp_path / "pacoca.log").exists()
    finally:
        for handler in list(root.handlers):
            if getattr(handler, "_pacoca_handler", False):
                root.removeHandler(handler)
                handler.close()
        root.handlers[:] = [h for h in root.handlers if not getattr(h, "_pacoca_handler", False)]
        root.setLevel(logging.WARNING)

def test_setup_logging_redacts_to_file(tmp_path):
    from core.config import Config
    from core.logger import setup_logging

    config = Config.__new__(Config)
    config.get = lambda key, default=None: {
        "logging.level": "INFO",
        "logging.file": str(tmp_path / "pacoca.log"),
        "logging.max_mb": 1,
    }.get(key, default)

    root = logging.getLogger()
    try:
        setup_logging(config)
        logging.getLogger("test_logger").error("password=segredo")
        for handler in root.handlers:
            if getattr(handler, "_pacoca_handler", False):
                handler.flush()
        assert "segredo" not in (tmp_path / "pacoca.log").read_text(encoding="utf-8")
    finally:
        for handler in list(root.handlers):
            if getattr(handler, "_pacoca_handler", False):
                root.removeHandler(handler)
                handler.close()
        root.setLevel(logging.WARNING)
