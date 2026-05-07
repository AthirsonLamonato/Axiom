"""
input/hotkeys.py — Atalhos de teclado globais
Registra hotkeys que disparam ações sem precisar da wake word.
"""

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)


# Mapeamento padrão de hotkeys
# Pode ser sobrescrito via config.yaml no futuro
DEFAULT_HOTKEYS = {
    "ctrl+shift+a": "toggle_listen",      # ativa/pausa escuta
    "ctrl+shift+t": "start_transcription", # inicia transcrição
    "ctrl+shift+s": "stop_transcription",  # para transcrição
    "ctrl+shift+space": "push_to_talk",    # fala um comando (sem wake word)
}


class HotkeyManager:
    def __init__(self, config, dispatcher: Callable):
        self.config = config
        self.dispatcher = dispatcher
        self._thread = None
        self._active = False

    def start(self):
        """Inicia o listener de hotkeys em thread separada."""
        try:
            import keyboard
        except ImportError:
            logger.warning("Biblioteca 'keyboard' não instalada. Hotkeys desabilitadas.")
            return

        self._active = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        logger.info("HotkeyManager iniciado")

    def _listen(self):
        import keyboard

        for hotkey, action in DEFAULT_HOTKEYS.items():
            keyboard.add_hotkey(
                hotkey,
                lambda a=action: self._handle(a),
                suppress=False,
            )
        logger.debug(f"Hotkeys registradas: {list(DEFAULT_HOTKEYS.keys())}")
        keyboard.wait()  # bloqueia a thread

    def _handle(self, action: str):
        logger.debug(f"Hotkey acionada: {action}")
        self.dispatcher(action)

    def stop(self):
        self._active = False
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
