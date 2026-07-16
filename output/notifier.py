"""
output/notifier.py — Notificações de desktop multiplataforma
"""

import logging
import platform
import threading
import warnings

logger = logging.getLogger(__name__)


def _load_windows_balloon():
    from plyer.platforms.win.libs.balloontip import balloon_tip
    return balloon_tip


def _notify_windows(title: str, message: str) -> None:
    """Executa o backend do Windows dentro de uma thread protegida.

    O plyer cria uma thread sem tratamento de exceção. Quando o Explorer ou a
    bandeja não estão disponíveis, isso polui o terminal mesmo que a chamada
    externa esteja em um try/except. Controlar a thread aqui mantém notificações
    opcionais e nunca derruba (nem assusta) a sessão principal.
    """
    try:
        _load_windows_balloon()(
            title=title,
            message=message,
            app_name="Paçoca",
            timeout=5,
        )
    except Exception as exc:
        logger.debug("Notificação do Windows falhou: %s", exc)


def notify(title: str, message: str):
    """Envia notificação desktop. Silencia erros se plyer não estiver disponível."""
    try:
        if platform.system() == "Windows":
            threading.Thread(
                target=_notify_windows,
                args=(title, message),
                daemon=True,
                name="pacoca-notification",
            ).start()
            return

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
    except Exception as exc:
        logger.debug("Notificação falhou: %s", exc)
