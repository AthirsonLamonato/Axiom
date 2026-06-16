"""
output/overlay.py — Janela de desktop do Paçoca (PyQt6)
Thread-safe via queue + QTimer.

Quando `overlay.enabled: true` (ou sem `--no-overlay`), esta janela é a
"tela de desktop" do Paçoca: histórico de conversa, caixa de texto, botão
de microfone (captura um comando de voz único) e botão de conta Google
(Calendar/Drive). Quando desabilitada, nada disso existe — o assistente
roda só por texto/voz no terminal, exatamente como antes desta funcionalidade.
"""

import logging
import os
import platform
import threading
import queue
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


_NO_OPACITY = _is_wsl()  # WSL X11 não suporta opacidade de janela


def _has_display() -> bool:
    """
    Verifica se há display REALMENTE disponível antes de criar QApplication.
    Checa a existência do socket, não só a variável de ambiente.
    """
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return False
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return False

    if platform.system() == "Windows":
        return bool(os.environ.get("SESSIONNAME") or os.environ.get("DISPLAY"))

    wayland = os.environ.get("WAYLAND_DISPLAY", "")
    if wayland:
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        socket_path = wayland if wayland.startswith("/") else os.path.join(runtime, wayland)
        if os.path.exists(socket_path):
            return True

    display = os.environ.get("DISPLAY", "")
    if display:
        try:
            num = display.lstrip(":").split(".")[0]
            if os.path.exists(f"/tmp/.X{num}-lock"):
                return True
        except Exception:
            pass

    return False


_instance: "PacocaOverlay | None" = None
_msg_queue: queue.Queue = queue.Queue()
_orchestrator = None  # injetado via set_orchestrator() depois de criado em main.py
_voice = None         # VoiceInput lazy, criado no 1º clique do microfone

STATES = {
    "idle":       ("●", "#555577"),
    "listening":  ("◉", "#50A0FF"),
    "processing": ("◌", "#FFAA00"),
    "speaking":   ("◎", "#50FF90"),
}


class PacocaOverlay:
    def __init__(self, config):
        from PyQt6.QtWidgets import (
            QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout,
            QLineEdit, QPushButton, QTextEdit,
        )
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtGui import QFont

        self.config = config
        self.duration_ms = config.get("overlay.duration_ms", 4000)
        self._state = "idle"

        self._app = QApplication.instance() or QApplication(sys.argv)
        # Por padrão, fechar a última janela visível mata o QApplication —
        # como esta janela agora tem barra de título (clicável no X), isso
        # mataria o processo do Paçoca inteiro (incluindo a thread do
        # orchestrator). Fechar deve só ocultar, como toggle()/hide() já fazem.
        self._app.setQuitOnLastWindowClosed(False)
        self._window = QWidget()
        self._window.setWindowTitle("Paçoca")
        self._window.resize(440, 620)
        self._window.setStyleSheet("background: #0c0c16;")

        root = QVBoxLayout(self._window)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        # Header: estado + conta Google
        header = QHBoxLayout()
        self._state_dot = QLabel("●")
        self._state_dot.setFont(QFont("Segoe UI", 10))
        self._state_dot.setStyleSheet("color: #555577; background: transparent; border: none;")
        self._state_label = QLabel("Paçoca")
        self._state_label.setFont(QFont("Segoe UI", 10))
        self._state_label.setStyleSheet("color: #888899; background: transparent; border: none;")
        header.addWidget(self._state_dot)
        header.addWidget(self._state_label)
        header.addStretch()

        self._account_btn = QPushButton("Conectar Google")
        self._account_btn.setStyleSheet(
            "QPushButton { background: #1a1a2e; color: #8b9bff; border: 1px solid #2a2a4e;"
            " border-radius: 6px; padding: 4px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #22224a; }"
        )
        self._account_btn.clicked.connect(self._on_account_clicked)
        header.addWidget(self._account_btn)
        root.addLayout(header)

        # Histórico de conversa (log completo, não só as últimas mensagens)
        self._chat_log = QTextEdit()
        self._chat_log.setReadOnly(True)
        self._chat_log.setFont(QFont("Consolas", 10))
        self._chat_log.setStyleSheet(
            "background: #12121f; color: #d8d8e8; border: 1px solid rgba(80,160,255,0.15);"
            " border-radius: 8px; padding: 8px;"
        )
        root.addWidget(self._chat_log)

        # Caixa de texto + botões
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Digite um comando…")
        self._input.setFont(QFont("Segoe UI", 11))
        self._input.setStyleSheet(
            "background: #1a1a2e; color: #e0e0e0; border: 1px solid #2a2a4e;"
            " border-radius: 6px; padding: 6px 10px;"
        )
        self._input.returnPressed.connect(self._on_submit_text)
        input_row.addWidget(self._input)

        self._mic_btn = QPushButton("🎤")
        self._mic_btn.setFixedWidth(40)
        self._mic_btn.setStyleSheet(
            "QPushButton { background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 6px;"
            " font-size: 14px; }"
            "QPushButton:hover { background: #22224a; }"
        )
        self._mic_btn.clicked.connect(self._on_mic_clicked)
        input_row.addWidget(self._mic_btn)

        self._send_btn = QPushButton("Enviar")
        self._send_btn.setStyleSheet(
            "QPushButton { background: #2a4ad0; color: white; border: none; border-radius: 6px;"
            " padding: 6px 14px; }"
            "QPushButton:hover { background: #3a5ae0; }"
        )
        self._send_btn.clicked.connect(self._on_submit_text)
        input_row.addWidget(self._send_btn)

        root.addLayout(input_row)

        # Timer para poll da queue (100ms) — toda atualização vinda de outras
        # threads (orchestrator, voz, OAuth) passa por aqui para tocar a UI
        # só na thread do Qt.
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(100)

        self._refresh_account_status()
        self._center_window()
        logger.info("Janela de desktop inicializada")

    def _center_window(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        w, h = self._window.width(), self._window.height()
        self._window.move((screen.width() - w) // 2, (screen.height() - h) // 2)

    # ── Conta Google ───────────────────────────────────────────────────

    def _refresh_account_status(self):
        try:
            from modules.calendar_integration import TOKEN_PATH
            token_path = self.config.get("calendar.token_path", TOKEN_PATH)
            connected = os.path.exists(token_path)
        except Exception:
            connected = False
        if connected:
            self._account_btn.setText("Google ✓ conectado")
        else:
            self._account_btn.setText("Conectar Google")

    def _on_account_clicked(self):
        self._account_btn.setText("Conectando…")
        self._account_btn.setEnabled(False)
        threading.Thread(target=self._do_account_auth, daemon=True).start()

    def _do_account_auth(self):
        try:
            from modules.calendar_integration import auth_calendar
            result = auth_calendar()
        except Exception as e:
            result = f"Erro ao conectar: {e}"
        _msg_queue.put(("account_done", result))

    # ── Caixa de texto ────────────────────────────────────────────────

    def _on_submit_text(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._input.setEnabled(False)
        self._send_btn.setEnabled(False)
        self._append_chat("Você", text)
        threading.Thread(target=self._dispatch_command, args=(text, "texto"), daemon=True).start()

    # ── Microfone ───────────────────────────────────────────────────────

    def _on_mic_clicked(self):
        self._mic_btn.setEnabled(False)
        _msg_queue.put(("state_detail", "listening", "Ouvindo…"))
        threading.Thread(target=self._do_listen_once, daemon=True).start()

    def _do_listen_once(self):
        global _voice
        try:
            if _voice is None:
                from input.stt import init_voice
                _voice = init_voice(self.config)
            text = _voice.listen_once(timeout=8.0)
        except Exception as e:
            logger.warning("Captura de voz falhou: %s", e)
            _msg_queue.put(("mic_error", str(e)))
            return
        _msg_queue.put(("mic_done",))
        if text:
            _msg_queue.put(("chat", "Você (voz)", text))
            self._dispatch_command(text, "voz")
        else:
            _msg_queue.put(("state_detail", "idle", ""))

    # ── Dispatch (texto ou voz) ───────────────────────────────────────

    def _dispatch_command(self, text: str, origem: str):
        if _orchestrator is None:
            _msg_queue.put(("chat", "Paçoca", "Orchestrator não disponível ainda."))
            _msg_queue.put(("input_done",))
            return
        _msg_queue.put(("state_detail", "processing", "Processando"))
        try:
            _orchestrator._tts_done = False
            response = _orchestrator.dispatch_chain(text)
            if response:
                _msg_queue.put(("chat", "Paçoca", response))
                if not _orchestrator._tts_done:
                    _orchestrator.tts.speak(response)
        except Exception as e:
            logger.error("Erro ao despachar comando da janela: %s", e, exc_info=True)
            _msg_queue.put(("chat", "Paçoca", f"Erro: {e}"))
        finally:
            _msg_queue.put(("state_detail", "idle", ""))
            _msg_queue.put(("input_done",))

    # ── Poll da queue (thread Qt) ───────────────────────────────────────

    def _poll(self):
        try:
            while True:
                item = _msg_queue.get_nowait()
                cmd, args = item[0], item[1:]
                if cmd == "message":
                    self._append_chat("Paçoca", args[0])
                elif cmd == "chat":
                    self._append_chat(args[0], args[1])
                elif cmd == "state":
                    self._do_set_state(args[0])
                elif cmd == "state_detail":
                    self._do_set_state_detail(args[0], args[1])
                elif cmd == "show":
                    self._window.show()
                elif cmd == "hide":
                    self._window.hide()
                elif cmd == "account_done":
                    self._append_chat("Paçoca", args[0])
                    self._refresh_account_status()
                    self._account_btn.setEnabled(True)
                elif cmd == "mic_done":
                    self._mic_btn.setEnabled(True)
                elif cmd == "mic_error":
                    self._append_chat("Paçoca", f"Não consegui usar o microfone: {args[0]}")
                    self._mic_btn.setEnabled(True)
                    self._do_set_state_detail("idle", "")
                elif cmd == "input_done":
                    self._input.setEnabled(True)
                    self._send_btn.setEnabled(True)
                    self._input.setFocus()
        except queue.Empty:
            pass

    def _append_chat(self, who: str, text: str):
        if not text:
            return
        self._window.show()
        self._chat_log.append(f"<b>{who}:</b> {text}")
        self._chat_log.verticalScrollBar().setValue(self._chat_log.verticalScrollBar().maximum())

    def _do_set_state(self, state: str):
        self._do_set_state_detail(state, "")

    def _do_set_state_detail(self, state: str, detail: str):
        self._state = state
        dot, color = STATES.get(state, ("●", "#555577"))
        self._state_dot.setText(dot)
        self._state_dot.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        self._state_label.setText(detail if detail else state.capitalize())

    def run(self):
        self._window.show()
        self._app.exec()


# ── Interface pública thread-safe ─────────────────────────────────────

def init(config):
    global _instance
    if not _has_display():
        logger.info("Janela de desktop desabilitada: sem display disponível (DISPLAY=%s, WAYLAND=%s)",
                    os.environ.get("DISPLAY", ""), os.environ.get("WAYLAND_DISPLAY", ""))
        return
    try:
        _instance = PacocaOverlay(config)
        logger.info("Janela de desktop inicializada (aguardando run_main_loop)")

        try:
            import keyboard
            keyboard.add_hotkey("ctrl+shift+a", toggle, suppress=False)
        except Exception:
            pass

    except ImportError:
        logger.warning("PyQt6 não instalado. Janela de desktop desabilitada.")
    except Exception as e:
        logger.warning("Janela de desktop desabilitada (plugin Qt não carregou): %s", e)


def set_orchestrator(orchestrator) -> None:
    """Injeta a instância do Orchestrator — chamado por main.py depois que
    ela é criada (a janela é inicializada antes disso). A caixa de texto e o
    botão de microfone usam essa referência para despachar comandos."""
    global _orchestrator
    _orchestrator = orchestrator


def run_main_loop():
    """Executa o event loop do Qt na main thread. Bloqueante."""
    if _instance:
        _instance.run()


def show_message(text: str, duration_ms: int = None):
    if _instance:
        _msg_queue.put(("message", text))


def set_state(state: str):
    """Define estado visual: idle | listening | processing | speaking"""
    if _instance:
        _msg_queue.put(("state", state))


def set_state_detail(state: str, detail: str):
    """Define estado visual com rótulo descritivo. Ex: processing, 'Consultando Groq'"""
    if _instance:
        _msg_queue.put(("state_detail", state, detail))


def show(*_) -> str:
    if _instance:
        _msg_queue.put(("show",))
    return "Janela de desktop exibida."


def hide(*_) -> str:
    if _instance:
        _msg_queue.put(("hide",))
    return "Janela de desktop ocultada."


def toggle(*_) -> str:
    if _instance:
        if _instance._window.isVisible():
            return hide()
        return show()
    return "Janela de desktop não disponível."
