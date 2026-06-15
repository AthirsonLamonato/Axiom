"""
output/overlay.py — Overlay flutuante com PyQt6
Thread-safe via queue + QTimer. Suporta fade, estado e histórico.
"""

import logging
import threading
import queue
import sys
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False

_NO_OPACITY = _is_wsl()  # WSL X11 não suporta opacidade de janela

_instance: "PacocaOverlay | None" = None
_msg_queue: queue.Queue = queue.Queue()

STATES = {
    "idle":       ("●", "#555577"),
    "listening":  ("◉", "#50A0FF"),
    "processing": ("◌", "#FFAA00"),
    "speaking":   ("◎", "#50FF90"),
}


class PacocaOverlay:
    def __init__(self, config):
        from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout
        from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
        from PyQt6.QtGui import QFont

        self.config = config
        self.duration_ms = config.get("overlay.duration_ms", 4000)
        self._position = config.get("overlay.position", "top-right")
        self._history: deque = deque(maxlen=3)
        self._state = "idle"
        self._hide_timer = None

        self._app = QApplication.instance() or QApplication(sys.argv)
        self._window = QWidget()
        self._window.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        if not _NO_OPACITY:
            self._window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self._window.setWindowOpacity(0.0)

        root_layout = QVBoxLayout(self._window)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        container = QWidget()
        container.setStyleSheet(
            "background: rgba(12, 12, 22, 220);"
            "border-radius: 10px;"
            "border: 1px solid rgba(80, 160, 255, 0.25);"
        )
        root_layout.addWidget(container)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(14, 10, 14, 10)
        inner.setSpacing(4)

        # Header: estado
        header = QHBoxLayout()
        self._state_dot = QLabel("●")
        self._state_dot.setFont(QFont("Segoe UI", 9))
        self._state_dot.setStyleSheet("color: #555577; background: transparent; border: none;")
        self._state_label = QLabel("Paçoca")
        self._state_label.setFont(QFont("Segoe UI", 9))
        self._state_label.setStyleSheet("color: #888899; background: transparent; border: none;")
        header.addWidget(self._state_dot)
        header.addWidget(self._state_label)
        header.addStretch()
        inner.addLayout(header)

        # Mensagem principal
        self._msg_label = QLabel("")
        self._msg_label.setWordWrap(True)
        self._msg_label.setMaximumWidth(360)
        self._msg_label.setFont(QFont("Consolas", 11))
        self._msg_label.setStyleSheet("color: #E0E0E0; background: transparent; border: none;")
        inner.addWidget(self._msg_label)

        # Histórico
        self._history_label = QLabel("")
        self._history_label.setWordWrap(True)
        self._history_label.setMaximumWidth(360)
        self._history_label.setFont(QFont("Consolas", 9))
        self._history_label.setStyleSheet("color: #666688; background: transparent; border: none;")
        inner.addWidget(self._history_label)

        # Animação de opacidade (desativada em WSL — X11 não suporta)
        if not _NO_OPACITY:
            self._anim = QPropertyAnimation(self._window, b"windowOpacity")
            self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        else:
            self._anim = None

        # Timer para poll da queue (100ms)
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(100)

        # Hide timer
        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

        self._position_window()
        logger.info("Overlay inicializado")

    def _position_window(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self._window.adjustSize()
        w, h = self._window.sizeHint().width() + 20, self._window.sizeHint().height() + 20
        margin = 20

        positions = {
            "top-left":     (margin, margin),
            "top-right":    (screen.width() - w - margin, margin),
            "bottom-left":  (margin, screen.height() - h - margin),
            "bottom-right": (screen.width() - w - margin, screen.height() - h - margin),
        }
        x, y = positions.get(self._position, positions["top-right"])
        self._window.move(x, y)

    def _poll(self):
        """Processa mensagens da queue no thread Qt."""
        try:
            while True:
                cmd, *args = _msg_queue.get_nowait()
                if cmd == "message":
                    self._do_show_message(*args)
                elif cmd == "state":
                    self._do_set_state(*args)
                elif cmd == "show":
                    self._fade_in()
                elif cmd == "hide":
                    self._fade_out()
        except queue.Empty:
            pass

    def _do_show_message(self, text: str, duration_ms: int):
        if text:
            self._history.appendleft(text)

        self._msg_label.setText(text)
        self._history_label.setText("\n".join(list(self._history)[1:]))
        self._window.adjustSize()
        self._position_window()

        self._fade_in()
        self._hide_timer.stop()
        self._hide_timer.start(duration_ms)

    def _do_set_state(self, state: str):
        self._state = state
        dot, color = STATES.get(state, ("●", "#555577"))
        self._state_dot.setText(dot)
        self._state_dot.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        self._state_label.setText(state.capitalize())
        # Mostra a janela quando ativo, esconde quando ocioso (sem mensagem pendente)
        if state == "idle":
            if not self._msg_label.text():
                self._fade_out()
        else:
            self._fade_in()

    def _fade_in(self):
        if self._anim is None:
            self._window.show()
            return
        self._window.show()
        self._anim.stop()
        self._anim.setDuration(200)
        self._anim.setStartValue(self._window.windowOpacity())
        self._anim.setEndValue(self.config.get("overlay.opacity", 0.92))
        self._anim.start()

    def _fade_out(self):
        if self._anim is None:
            self._window.hide()
            return
        self._anim.stop()
        self._anim.setDuration(400)
        self._anim.setStartValue(self._window.windowOpacity())
        self._anim.setEndValue(0.0)
        try:
            self._anim.finished.disconnect()
        except Exception:
            pass
        self._anim.finished.connect(self._window.hide)
        self._anim.start()

    def run(self):
        self._app.exec()


# ── Interface pública thread-safe ─────────────────────────────────────

def init(config):
    global _instance
    try:
        _instance = PacocaOverlay(config)
        logger.info("Overlay inicializado (aguardando run_main_loop)")

        try:
            import keyboard
            keyboard.add_hotkey("ctrl+shift+a", toggle, suppress=False)
        except Exception:
            pass

    except ImportError:
        logger.warning("PyQt6 não instalado. Overlay desabilitado.")


def run_main_loop():
    """Executa o event loop do Qt na main thread. Bloqueante."""
    if _instance:
        _instance.run()


def show_message(text: str, duration_ms: int = None):
    if _instance:
        ms = duration_ms or _instance.duration_ms
        _msg_queue.put(("message", text, ms))


def set_state(state: str):
    """Define estado visual: idle | listening | processing | speaking"""
    if _instance:
        _msg_queue.put(("state", state))


def show(*_) -> str:
    if _instance:
        _msg_queue.put(("show",))
    return "Overlay exibido."


def hide(*_) -> str:
    if _instance:
        _msg_queue.put(("hide",))
    return "Overlay ocultado."


def toggle(*_) -> str:
    if _instance:
        if _instance._window.isVisible():
            return hide()
        return show()
    return "Overlay não disponível."
