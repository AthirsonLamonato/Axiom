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
        logger.debug("Hotkeys registradas: %s", list(DEFAULT_HOTKEYS.keys()))
        keyboard.wait()

    def _handle(self, action: str):
        logger.debug("Hotkey acionada: %s", action)

        if action == "push_to_talk":
            threading.Thread(target=self._push_to_talk, daemon=True).start()
            return

        if action in ("start_transcription", "stop_transcription"):
            threading.Thread(
                target=self._call_transcription, args=(action,), daemon=True
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

        try:
            from output import overlay
            overlay.set_state_detail("listening", "Ouvindo (push-to-talk)…")
        except Exception:
            pass

        try:
            # _capture_and_transcribe usa o limiar de energia calibrado
            text = vi._capture_and_transcribe()
            if text.strip():
                self.dispatcher(text)
        except Exception as e:
            logger.error("push_to_talk falhou: %s", e, exc_info=True)
        finally:
            try:
                from output import overlay
                overlay.set_state("idle")
            except Exception:
                pass

    def _call_transcription(self, action: str):
        """Chama start/stop da transcrição pelo módulo correto."""
        try:
            from modules import transcription
            fn = transcription.start if action == "start_transcription" else transcription.stop
            result = fn()
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
