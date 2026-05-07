"""
core/logger.py — Configuração centralizada de logging
Chame setup_logging() no início do main.py
"""

import logging
import logging.handlers
import os
from core.config import Config


def setup_logging(config: Config):
    level_str = config.get("logging.level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)

    log_file = config.get("logging.file", "logs/axiom.log")
    max_mb = config.get("logging.max_mb", 10)

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    formatter = logging.Formatter(
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

    # Handler de console (só WARNING+ para não poluir o terminal)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter("%(levelname)s  %(message)s"))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
