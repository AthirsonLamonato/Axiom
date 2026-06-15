"""
modules/meeting_detector.py — Detecção automática de videochamadas
Monitora processos ativos e ativa perfil/transcrição ao detectar Zoom, Teams, etc.
"""

import logging
import platform
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)
OS = platform.system()

MEETING_PROCESSES = {
    "zoom":           "Zoom",
    "teams":          "Microsoft Teams",
    "slack":          "Slack",
    "webex":          "Webex",
    "discord":        "Discord",
    "skype":          "Skype",
    "whereby":        "Whereby",
    "loom":           "Loom",
}

# Palavras-chave nos títulos de janela de browsers para detectar reuniões via web
MEETING_WINDOW_TITLES = [
    "meet.google.com",
    "Google Meet",
    "Zoom Meeting",
    "Microsoft Teams",
    "Whereby",
    "Jitsi Meet",
    "BigBlueButton",
]

_monitoring    = False
_in_meeting    = False
_monitor_thread: Optional[threading.Thread] = None
_prev_profile  = "work"
_CHECK_INTERVAL = 15   # segundos entre verificações


def _get_running_process_names() -> list:
    try:
        import psutil
        return [p.name().lower() for p in psutil.process_iter(["name"])]
    except Exception:
        return []


def _get_window_titles() -> list[str]:
    """Retorna títulos das janelas abertas (Linux via xdotool, Windows via win32gui)."""
    titles: list[str] = []
    if OS == "Linux":
        try:
            import subprocess
            out = subprocess.check_output(
                ["xdotool", "search", "--onlyvisible", "--name", ""],
                stderr=subprocess.DEVNULL, timeout=2,
            ).decode(errors="ignore")
            for wid in out.strip().splitlines():
                try:
                    title = subprocess.check_output(
                        ["xdotool", "getwindowname", wid.strip()],
                        stderr=subprocess.DEVNULL, timeout=1,
                    ).decode(errors="ignore").strip()
                    if title:
                        titles.append(title)
                except Exception:
                    pass
        except Exception:
            pass
    elif OS == "Windows":
        try:
            import win32gui
            def _cb(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    t = win32gui.GetWindowText(hwnd)
                    if t:
                        titles.append(t)
            win32gui.EnumWindows(_cb, None)
        except Exception:
            pass
    return titles


def _detect_meeting_app() -> Optional[str]:
    procs = _get_running_process_names()
    for proc_key, display_name in MEETING_PROCESSES.items():
        if any(proc_key in p for p in procs):
            return display_name

    # Detecta reuniões via browser (Google Meet, Jitsi, etc.) pelo título de janela
    try:
        titles = _get_window_titles()
        for title in titles:
            for kw in MEETING_WINDOW_TITLES:
                if kw.lower() in title.lower():
                    return kw
    except Exception:
        pass

    return None


def _on_meeting_start(app_name: str) -> None:
    global _in_meeting, _prev_profile
    _in_meeting = True
    logger.info("Reunião detectada: %s", app_name)

    try:
        from core.profiles import _get_manager
        mgr = _get_manager()
        _prev_profile = mgr.active
        mgr.switch("meeting")
    except Exception:
        pass

    try:
        from modules import transcription
        from core.config import Config
        transcription.start("sistema")   # loopback
    except Exception:
        pass

    try:
        from output.notifier import notify
        notify("Axiom", f"Reunião detectada ({app_name}). Transcrição iniciada.")
    except Exception:
        pass
    try:
        from web.app import push_event
        push_event("meeting", f"🟢 Reunião detectada: {app_name}")
    except Exception:
        pass

    print(f"\n[Axiom] Reunião detectada: {app_name}. Perfil → meeting, transcrição iniciada.")


def _on_meeting_end() -> None:
    global _in_meeting
    _in_meeting = False
    logger.info("Reunião encerrada.")

    try:
        from modules import transcription
        transcription.stop()
    except Exception:
        pass

    try:
        from core.profiles import _get_manager
        _get_manager().switch(_prev_profile)
    except Exception:
        pass

    try:
        from output.notifier import notify
        notify("Axiom", "Reunião encerrada. Transcrição salva.")
    except Exception:
        pass
    try:
        from web.app import push_event
        push_event("meeting", "🔴 Reunião encerrada. Transcrição salva.")
    except Exception:
        pass

    print("\n[Axiom] Reunião encerrada. Transcrição salva. Perfil restaurado.")


def _monitor_loop() -> None:
    global _in_meeting
    while _monitoring:
        app = _detect_meeting_app()
        if app and not _in_meeting:
            _on_meeting_start(app)
        elif not app and _in_meeting:
            _on_meeting_end()
        time.sleep(_CHECK_INTERVAL)


# ── Comandos públicos ─────────────────────────────────────────────────

def start_monitoring(*_) -> str:
    global _monitoring, _monitor_thread
    if _monitoring:
        return "Detector de reunião já está ativo."
    _monitoring = True
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
    _monitor_thread.start()
    apps = ", ".join(MEETING_PROCESSES.values())
    return f"Detector de reunião ativado. Monitorando: {apps}."


def stop_monitoring(*_) -> str:
    global _monitoring
    if not _monitoring:
        return "Detector de reunião não está ativo."
    _monitoring = False
    return "Detector de reunião desativado."


def status(*_) -> str:
    if not _monitoring:
        return "Detector de reunião: inativo."
    app = _detect_meeting_app()
    if app:
        return f"Reunião em andamento: {app}."
    return "Detector ativo. Nenhuma reunião detectada no momento."
