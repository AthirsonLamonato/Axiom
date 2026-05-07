"""
output/overlay.py — Overlay flutuante com PyQt6
Dashboard sempre visível no canto da tela.
"""

import logging
import threading
import sys

logger = logging.getLogger(__name__)

_overlay_instance = None
_app_instance = None


class AxiomOverlay:
    """Janela flutuante transparente com PyQt6."""

    def __init__(self, config):
        from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
        from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
        from PyQt6.QtGui import QFont, QColor

        self.config = config
        self.duration_ms = config.get("overlay.duration_ms", 4000)
        position = config.get("overlay.position", "top-left")

        self._app = QApplication.instance() or QApplication(sys.argv)
        self._window = QWidget()
        self._window.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self._window)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(380)
        self._label.setFont(QFont("JetBrains Mono, Consolas, Courier New", 11))
        self._label.setStyleSheet(
            "color: #E0E0E0;"
            "background: rgba(15, 15, 25, 210);"
            "padding: 12px 16px;"
            "border-radius: 10px;"
            "border: 1px solid rgba(80, 160, 255, 0.3);"
        )
        layout.addWidget(self._label)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._window.hide)

        self._position_window(position)
        logger.info("Overlay inicializado")

    def _position_window(self, position: str):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        margin = 20
        self._window.adjustSize()
        w, h = 400, 80

        if position == "top-left":
            self._window.move(margin, margin)
        elif position == "top-right":
            self._window.move(screen.width() - w - margin, margin)
        elif position == "bottom-left":
            self._window.move(margin, screen.height() - h - margin)
        elif position == "bottom-right":
            self._window.move(screen.width() - w - margin, screen.height() - h - margin)

    def show_message(self, text: str, duration_ms: int = None):
        if duration_ms is None:
            duration_ms = self.duration_ms
        self._label.setText(text)
        self._label.adjustSize()
        self._window.adjustSize()
        self._window.show()
        self._timer.start(duration_ms)

    def hide(self):
        self._window.hide()

    def show(self):
        self._window.show()

    def run(self):
        self._app.exec()


# ── Interface pública (thread-safe) ───────────────────────────────────

def init(config):
    global _overlay_instance
    try:
        _overlay_instance = AxiomOverlay(config)
        thread = threading.Thread(target=_overlay_instance.run, daemon=True)
        thread.start()
        logger.info("Overlay rodando em thread separada")
    except ImportError:
        logger.warning("PyQt6 não instalado. Overlay desabilitado.")


def show_message(text: str, duration_ms: int = None):
    if _overlay_instance:
        _overlay_instance.show_message(text, duration_ms)
    else:
        print(f"[Axiom] {text}")


def show(*_):
    """Torna o overlay visível sem nova mensagem."""
    if _overlay_instance:
        _overlay_instance.show()
    return "Overlay exibido."


def hide(*_):
    if _overlay_instance:
        _overlay_instance.hide()
    return "Overlay ocultado."
