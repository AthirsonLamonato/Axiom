"""
modules/security.py — Confirmação e whitelist de ações críticas
"""

import logging

logger = logging.getLogger(__name__)


def is_critical(command: str) -> bool:
    """Verifica se um comando está na lista de ações críticas."""
    from core.config import Config
    config = Config()
    critical = config.get("security.critical_commands", [])
    cmd = command.lower()
    return any(c.lower() in cmd for c in critical)


def confirm(action: str) -> bool:
    """Solicita confirmação via terminal."""
    print(f"\n  ⚠ Ação crítica detectada: '{action}'")
    resp = input("    Confirmar? (s/N): ").strip().lower()
    confirmed = resp == "s"
    logger.info(f"Confirmação para '{action}': {'sim' if confirmed else 'não'}")
    return confirmed
