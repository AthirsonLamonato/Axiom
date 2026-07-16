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
import html
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

    wayland = os.environ.get("WAYLAND_DISPLAY", "")
    if wayland:
        default_runtime = f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else ""
        runtime = os.environ.get("XDG_RUNTIME_DIR", default_runtime)
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

    if platform.system() == "Windows":
        # Em uma sessao Windows nativa, SESSIONNAME e o indicador confiavel.
        # DISPLAY sozinho pode vir de WSL/X11 e precisa passar pela checagem
        # de socket acima, como nos demais sistemas.
        return bool(os.environ.get("SESSIONNAME"))

    return False


_instance: "PacocaOverlay | None" = None
_msg_queue: queue.Queue = queue.Queue()
_orchestrator = None  # injetado via set_orchestrator() depois de criado em main.py
_voice = None         # VoiceInput lazy, criado no 1º clique do microfone

STATES = {
    "idle":       ("●", "#5d7a8c"),
    "listening":  ("●", "#00e5ff"),
    "processing": ("●", "#f0883e"),
    "speaking":   ("●", "#3fb950"),
}

# Layout escuro "cyber" é fixo; só a cor de destaque (botão enviar, hover,
# bordas acentuadas, texto do botão de conta) muda por tema neon. Selecionável
# via overlay.theme no config.yaml.
THEMES = {
    "blue":   {"accent": "#0090a8", "accent_hover": "#00b8d4", "accent_text": "#00e5ff", "accent_glow": "#00e5ff"},
    "green":  {"accent": "#0a8f5b", "accent_hover": "#12b377", "accent_text": "#39ffb0", "accent_glow": "#39ffb0"},
    "purple": {"accent": "#7c2fd6", "accent_hover": "#9747ff", "accent_text": "#c87bff", "accent_glow": "#c87bff"},
    "orange": {"accent": "#c2570a", "accent_hover": "#e06f12", "accent_text": "#ff9d3d", "accent_glow": "#ff9d3d"},
}
DEFAULT_THEME = "blue"

UI = {
    "bg": "#04060c",
    "bg_2": "#0a1622",
    "card": "rgba(13, 22, 36, 235)",
    "card_alt": "#070d16",
    "border": "rgba(0, 229, 255, 46)",
    "border_focus": "rgba(0, 229, 255, 102)",
    "text": "#d8f3ff",
    "muted": "#5d7a8c",
    "response": "#3df0ff",
    "danger": "#f85149",
}


def _glow(widget, color: str, blur: int = 24, strength: int = 200):
    """Aplica um brilho neon sutil (drop shadow colorido) ao redor do widget."""
    from PyQt6.QtWidgets import QGraphicsDropShadowEffect
    from PyQt6.QtGui import QColor
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(blur)
    effect.setOffset(0, 0)
    qcolor = QColor(color)
    qcolor.setAlpha(strength)
    effect.setColor(qcolor)
    widget.setGraphicsEffect(effect)
    return effect


class PacocaOverlay:
    def __init__(self, config):
        from PyQt6.QtWidgets import (
            QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout,
            QLineEdit, QPushButton, QTextEdit, QGraphicsOpacityEffect,
        )
        from PyQt6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
        from PyQt6.QtGui import QFont

        self.config = config
        self.duration_ms = config.get("overlay.duration_ms", 4000)
        self._state = "idle"
        theme_name = config.get("overlay.theme", DEFAULT_THEME)
        self._theme = THEMES.get(theme_name, THEMES[DEFAULT_THEME])

        self._app = QApplication.instance() or QApplication(sys.argv)
        # Por padrão, fechar a última janela visível mata o QApplication —
        # como esta janela agora tem barra de título (clicável no X), isso
        # mataria o processo do Paçoca inteiro (incluindo a thread do
        # orchestrator). Fechar deve só ocultar, como toggle()/hide() já fazem.
        self._app.setQuitOnLastWindowClosed(False)
        self._window = QWidget()
        self._window.setWindowTitle("Paçoca")
        self._window.resize(520, 680)
        self._window.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f" stop:0 {UI['bg_2']}, stop:1 {UI['bg']}); color: {UI['text']};"
        )

        root = QVBoxLayout(self._window)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # Header: estado + conta Google
        header = QHBoxLayout()
        header.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self._title_label = QLabel("⚡ Paçoca")
        self._title_label.setFont(QFont("Segoe UI", 16))
        self._title_label.setStyleSheet(
            f"color: {self._theme['accent_text']}; background: transparent; border: none; letter-spacing: 2px;"
        )
        self._subtitle_label = QLabel("Assistente pessoal inteligente")
        self._subtitle_label.setFont(QFont("Segoe UI", 9))
        self._subtitle_label.setStyleSheet(f"color: {UI['muted']}; background: transparent; border: none;")
        title_box.addWidget(self._title_label)
        title_box.addWidget(self._subtitle_label)
        header.addLayout(title_box)
        header.addStretch()
        _glow(self._title_label, self._theme["accent_glow"], blur=28, strength=140)

        self._state_dot = QLabel("●")
        self._state_dot.setFont(QFont("Segoe UI", 11))
        self._state_dot.setStyleSheet(f"color: {UI['muted']}; background: transparent; border: none;")
        self._dot_opacity = QGraphicsOpacityEffect()
        self._state_dot.setGraphicsEffect(self._dot_opacity)
        self._dot_anim = QPropertyAnimation(self._dot_opacity, b"opacity")
        self._dot_anim.setDuration(1400)
        self._dot_anim.setKeyValueAt(0.0, 1.0)
        self._dot_anim.setKeyValueAt(0.5, 0.35)
        self._dot_anim.setKeyValueAt(1.0, 1.0)
        self._dot_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._dot_anim.setLoopCount(-1)
        self._state_label = QLabel("Paçoca")
        self._state_label.setFont(QFont("Segoe UI", 9))
        self._state_label.setStyleSheet(f"color: {UI['muted']}; background: transparent; border: none;")
        header.addWidget(self._state_dot)
        header.addWidget(self._state_label)

        self._account_btn = QPushButton("Conectar Google")
        self._account_btn.setStyleSheet(
            f"QPushButton {{ background: {UI['card']}; color: {self._theme['accent_text']};"
            f" border: 1px solid {UI['border_focus']}; border-radius: 6px; padding: 7px 11px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {UI['border']}; }}"
            f"QPushButton:disabled {{ color: {UI['muted']}; }}"
        )
        self._account_btn.clicked.connect(self._on_account_clicked)
        header.addWidget(self._account_btn)
        root.addLayout(header)

        divider = QLabel("Dashboard · Desktop · Comandos")
        divider.setFont(QFont("Segoe UI", 9))
        divider.setStyleSheet(
            f"color: {UI['muted']}; background: transparent; border-bottom: 1px solid {UI['border']}; padding: 0 0 10px 0;"
        )
        root.addWidget(divider)

        # Histórico de conversa (log completo, não só as últimas mensagens)
        self._chat_log = QTextEdit()
        self._chat_log.setReadOnly(True)
        self._chat_log.setFont(QFont("Segoe UI", 10))
        self._chat_log.setStyleSheet(
            f"QTextEdit {{ background: {UI['card']}; color: {UI['text']}; border: 1px solid {UI['border']};"
            " border-radius: 8px; padding: 10px; selection-background-color: #1f6feb; }}"
        )
        root.addWidget(self._chat_log)

        # Caixa de texto + botões
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Digite um comando…")
        self._input.setFont(QFont("Segoe UI", 11))
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {UI['card_alt']}; color: {UI['text']}; border: 1px solid {UI['border_focus']};"
            " border-radius: 6px; padding: 8px 12px; }}"
            f"QLineEdit:focus {{ border-color: {self._theme['accent_text']}; }}"
            f"QLineEdit:disabled {{ color: {UI['muted']}; }}"
        )
        self._input.returnPressed.connect(self._on_submit_text)
        input_row.addWidget(self._input)

        self._mic_btn = QPushButton("Mic")
        self._mic_btn.setFixedWidth(48)
        self._mic_btn.setStyleSheet(
            f"QPushButton {{ background: {UI['card']}; color: {UI['text']}; border: 1px solid {UI['border_focus']};"
            " border-radius: 6px; padding: 8px 10px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {UI['border']}; }}"
            f"QPushButton:disabled {{ color: {UI['muted']}; }}"
        )
        self._mic_btn.clicked.connect(self._on_mic_clicked)
        input_row.addWidget(self._mic_btn)

        self._send_btn = QPushButton("Enviar")
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background: {self._theme['accent']}; color: white; border: none; border-radius: 6px;"
            " padding: 8px 16px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {self._theme['accent_hover']}; }}"
            f"QPushButton:disabled {{ background: {UI['border']}; color: {UI['muted']}; }}"
        )
        self._send_btn.clicked.connect(self._on_submit_text)
        input_row.addWidget(self._send_btn)
        _glow(self._send_btn, self._theme["accent_glow"], blur=16, strength=130)

        root.addLayout(input_row)

        # Timer para poll da queue (100ms) — toda atualização vinda de outras
        # threads (orchestrator, voz, OAuth) passa por aqui para tocar a UI
        # só na thread do Qt.
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(100)

        self._refresh_account_status()
        self._position_window()
        self._apply_opacity()
        logger.info("Janela de desktop inicializada (tema: %s)", theme_name)

    def _position_window(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        w, h = self._window.width(), self._window.height()
        margin = 24
        corners = {
            "top-left": (margin, margin),
            "top-right": (screen.width() - w - margin, margin),
            "bottom-left": (margin, screen.height() - h - margin),
            "bottom-right": (screen.width() - w - margin, screen.height() - h - margin),
        }
        center = ((screen.width() - w) // 2, (screen.height() - h) // 2)
        position = self.config.get("overlay.position", "top-left")
        x, y = corners.get(position, center)
        self._window.move(x, y)

    def _apply_opacity(self):
        if _NO_OPACITY:
            return
        opacity = self.config.get("overlay.opacity", 0.92)
        self._window.setWindowOpacity(max(0.1, min(1.0, opacity)))

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
                elif cmd == "quit":
                    # app.quit() chamado de outra thread não é confiável em
                    # todos os backends Qt (testado: trava no Wayland/WSLg) —
                    # processa na própria thread do Qt, igual a todo o resto.
                    self._app.quit()
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
        safe_who = html.escape(who)
        safe_text = html.escape(text).replace("\n", "<br>")
        is_user = who.startswith("Você")
        accent = self._theme["accent_text"] if is_user else UI["response"]
        border = self._theme["accent_text"] if is_user else UI["border_focus"]
        bg = UI["card_alt"] if is_user else "#0a1420"
        self._chat_log.append(
            f"""
            <div style="margin: 8px 0; padding: 10px 12px; background: {bg};
                        border-left: 3px solid {border}; border-radius: 0 6px 6px 0;">
              <div style="color: {accent}; font-size: 11px; font-weight: 600; margin-bottom: 4px;">{safe_who}</div>
              <div style="color: {UI['text']}; font-size: 13px; line-height: 1.35;">{safe_text}</div>
            </div>
            """
        )
        self._chat_log.verticalScrollBar().setValue(self._chat_log.verticalScrollBar().maximum())

    def _do_set_state(self, state: str):
        self._do_set_state_detail(state, "")

    def _do_set_state_detail(self, state: str, detail: str):
        self._state = state
        dot, color = STATES.get(state, ("●", "#555577"))
        self._state_dot.setText(dot)
        self._state_dot.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        from PyQt6.QtCore import QAbstractAnimation
        if state == "idle":
            self._dot_anim.stop()
            self._dot_opacity.setOpacity(1.0)
        elif self._dot_anim.state() != QAbstractAnimation.State.Running:
            self._dot_anim.start()
        labels = {
            "idle": "Ocioso",
            "listening": "Ouvindo",
            "processing": "Processando",
            "speaking": "Falando",
        }
        self._state_label.setText(detail if detail else labels.get(state, state.capitalize()))

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


def request_quit() -> None:
    """
    Encerra o event loop do Qt (run_main_loop() retorna), permitindo o
    processo terminar. Chamado por main.py quando o loop de texto/voz no
    terminal termina (ex: usuário digita 'sair') — sem isso, a janela de
    desktop manteria o processo vivo indefinidamente mesmo depois do
    terminal "encerrar".
    """
    if _instance:
        _msg_queue.put(("quit",))
