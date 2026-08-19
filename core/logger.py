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

    log_file = str(config.get("logging.file", "logs/pacoca.log"))
    try:
        max_mb = max(float(config.get("logging.max_mb", 10)), 1)
    except (TypeError, ValueError):
        max_mb = 10

    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = RedactingFormatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    # Evita duplicação quando o aplicativo é reinicializado no mesmo processo
    # (comum em testes, dashboard e durante o desenvolvimento).
    for handler in list(root.handlers):
        if getattr(handler, "_pacoca_handler", False):
            root.removeHandler(handler)
            handler.close()

    # Handler rotativo de arquivo
    file_handler = logging.handlers.RotatingFileHandler(

        log_file,
        maxBytes=max_mb * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SensitiveDataFilter())
    file_handler._pacoca_handler = True

    # Handler de console (só WARNING+ para não poluir o terminal)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(RedactingFormatter("%(levelname)s  %(message)s"))
    console_handler.addFilter(SensitiveDataFilter())
    console_handler._pacoca_handler = True

    root.setLevel(level)

    root.addHandler(file_handler)
    root.addHandler(console_handler)
