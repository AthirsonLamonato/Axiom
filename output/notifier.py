"""
output/notifier.py — Notificações de desktop multiplataforma
"""

import logging

logger = logging.getLogger(__name__)


def notify(title: str, message: str):
    """Envia notificação desktop. Silencia erros se plyer não estiver disponível."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Paçoca",
            timeout=5,
        )
    except ImportError:
        # Fallback: apenas loga
        logger.debug(f"[notify] {title}: {message}")
    except Exception as e:
        logger.debug(f"Notificação falhou: {e}")
