"""
core/logger.py — Configuração centralizada de logging
Chame setup_logging() no início do main.py
"""

import logging
import logging.handlers
import os
import re
from core.config import Config


_EMAIL_RE = re.compile(r"\b([\w.+-])[^@\s]*@([\w.-]+\.[A-Za-z]{2,})\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|access[_-]?token|refresh[_-]?token|authorization|password|senha)"
    r"(\s*[=:]\s*|\s+)([^\s,;]+)"
)


def redact_sensitive(value: object) -> str:
    """Remove destinatários e segredos comuns de qualquer texto de log."""
    text = str(value)
    text = _EMAIL_RE.sub(r"\1***@\2", text)
    text = _PHONE_RE.sub("[PHONE_REDACTED]", text)
    text = _SECRET_RE.sub(r"\1\2[SECRET_REDACTED]", text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Redige depois da interpolação de ``logging`` e antes da emissão."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive(record.getMessage())
        record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    """Também cobre traceback e demais campos adicionados pelo formatter."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive(super().format(record))


def setup_logging(config: Config):
    level_str = config.get("logging.level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)

    log_file = config.get("logging.file", "logs/pacoca.log")
    max_mb = config.get("logging.max_mb", 10)

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    formatter = RedactingFormatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler rotativo de arquivo
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_mb * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SensitiveDataFilter())

    # Handler de console (só WARNING+ para não poluir o terminal)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(RedactingFormatter("%(levelname)s  %(message)s"))
    console_handler.addFilter(SensitiveDataFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
