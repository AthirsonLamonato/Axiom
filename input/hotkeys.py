"""
input/hotkeys.py — Atalhos de teclado globais
Registra hotkeys que disparam ações sem precisar da wake word.
"""

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

# ctrl+shift+a é registrado pelo overlay.py diretamente (toggle show/hide).
# Aqui ficam apenas os atalhos cujas ações precisam de lógica de módulo.
DEFAULT_HOTKEYS = {
    "ctrl+shift+t":     "start_transcription",
    "ctrl+shift+s":     "stop_transcription",
    "ctrl+shift+space": "push_to_talk",
}


class HotkeyManager:
    def __init__(self, config, dispatcher: Callable):
        self.config = config
        self.dispatcher = dispatcher
        self._thread = None
        self._active = False

    def start(self) -> bool:
        """Registra os atalhos e inicia o listener. Retorna se ficou ativo."""
        try:
            import keyboard
        except ImportError:
            logger.warning("Biblioteca 'keyboard' não instalada. Hotkeys desabilitadas.")
            return False

        try:
            for hotkey, action in DEFAULT_HOTKEYS.items():
                keyboard.add_hotkey(
                    hotkey,
                    lambda a=action: self._handle(a),
                    suppress=False,
                )
            self._active = True
            self._thread = threading.Thread(
                target=keyboard.wait,
                daemon=True,
                name="pacoca-hotkeys",
            )
            self._thread.start()
            logger.info("Hotkeys registradas: %s", list(DEFAULT_HOTKEYS.keys()))
            return True
        except Exception as exc:
            logger.warning("Não foi possível registrar hotkeys: %s", exc)
            self._active = False
            return False

    def _handle(self, action: str):
        logger.debug("Hotkey acionada: %s", action)

        if action == "push_to_talk":
            self._push_to_talk()
            return

        if action in ("start_transcription", "stop_transcription"):
            threading.Thread(
                target=self._call_transcription,
                args=(action,),
                daemon=True,
                name=f"pacoca-{action}",
            ).start()
            return

        # Fallback: envia como comando de texto
        self.dispatcher(action)

    def _push_to_talk(self):
        """Captura um comando por voz imediatamente (sem wake word)."""
        from input.stt import get_instance
        vi = get_instance()
        if vi is None:
            logger.warning("push_to_talk: STT não inicializado (modo texto ativo?)")
            return

        vi.request_push_to_talk()

    def _call_transcription(self, action: str):
        """Chama start/stop da transcrição pelo módulo correto."""
        try:
            command = (
                "começa a transcrever"
                if action == "start_transcription"
                else "para a transcrição"
            )
            result = self.dispatcher(command)
            logger.info("Transcrição hotkey: %s → %s", action, result)
        except Exception as e:
            logger.error("Transcrição hotkey %s falhou: %s", action, e, exc_info=True)

    def stop(self):
        self._active = False
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
