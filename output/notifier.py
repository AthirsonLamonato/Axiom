"""
output/notifier.py — Notificações de desktop multiplataforma
"""

import logging
import warnings

logger = logging.getLogger(__name__)


def notify(title: str, message: str):
    """Envia notificação desktop. Silencia erros se plyer não estiver disponível."""
    try:
        from plyer import notification
        # plyer emite UserWarning quando dbus/notify-send não estão instalados
        # (comum em WSL/containers sem ambiente de desktop) — já tratamos a
        # ausência de notificação como não-fatal abaixo, então o aviso é ruído.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
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
