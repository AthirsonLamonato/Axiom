"""
modules/productivity.py — Monitoramento de uso e timer de foco (Pomodoro)
"""

import logging
import time
import threading
from collections import defaultdict
from datetime import datetime, date

logger = logging.getLogger(__name__)

_tracker: "UsageTracker | None" = None
_pomodoro: "PomodoroTimer | None" = None


# ── Rastreamento de uso ────────────────────────────────────────────────

class UsageTracker:
    def __init__(self, interval: int = 10):
        self.interval = interval
        self._usage: dict = defaultdict(float)
        self._running = False
        self._thread: "threading.Thread | None" = None
        self._date = date.today()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("UsageTracker iniciado")

    def stop(self):
        self._running = False

    def _loop(self):
        import psutil
        while self._running:
            if date.today() != self._date:
                self._usage.clear()
                self._date = date.today()
            try:
                for proc in psutil.process_iter(["name", "status", "cpu_percent"]):
                    if proc.info["status"] == "running":
                        self._usage[proc.info["name"]] += self.interval
            except Exception:
                pass
            time.sleep(self.interval)

    def top_apps(self, n: int = 8) -> list:
        return sorted(self._usage.items(), key=lambda x: x[1], reverse=True)[:n]

    def summary(self) -> str:
        tops = self.top_apps()
        if not tops:
            return "Nenhum dado de uso disponível ainda."
        lines = [f"Uso de apps — {self._date.strftime('%d/%m/%Y')}:"]
        for name, secs in tops:
            h, m = divmod(int(secs) // 60, 60)
            label = f"{h}h {m:02d}m" if h else f"{m}m"
            lines.append(f"  {name:<30} {label}")
        return "\n".join(lines)


# ── Timer de foco (Pomodoro) ───────────────────────────────────────────

class PomodoroTimer:
    def __init__(self, minutes: int, on_finish=None):
        self.minutes = minutes
        self.on_finish = on_finish
        self._thread: "threading.Thread | None" = None
        self._running = False
        self._started_at: "datetime | None" = None

    def start(self) -> str:
        if self._running:
            elapsed = int((datetime.now() - self._started_at).total_seconds() // 60)
            remaining = self.minutes - elapsed
            return f"Timer já ativo: {remaining} minutos restantes."
        self._running = True
        self._started_at = datetime.now()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return f"Timer de foco iniciado: {self.minutes} minutos. Bom trabalho!"

    def stop(self) -> str:
        if not self._running:
            return "Nenhum timer ativo."
        self._running = False
        return "Timer cancelado."

    def status(self) -> str:
        if not self._running:
            return "Nenhum timer ativo."
        elapsed = int((datetime.now() - self._started_at).total_seconds())
        remaining = self.minutes * 60 - elapsed
        if remaining <= 0:
            return "Timer concluído."
        m, s = divmod(remaining, 60)
        return f"Timer de foco: {m:02d}:{s:02d} restantes."

    def _run(self):
        time.sleep(self.minutes * 60)
        if not self._running:
            return
        self._running = False
        from output.notifier import notify
        notify("Axiom — Pomodoro", f"Sessão de {self.minutes} minutos concluída! Descanse.")
        try:
            from output import overlay
            overlay.show_message(f"Pomodoro concluído! {self.minutes} min de foco.", duration_ms=8000)
        except Exception:
            pass
        if self.on_finish:
            self.on_finish()
        logger.info(f"Pomodoro {self.minutes}min concluído")


# ── Interface pública ──────────────────────────────────────────────────

def start_tracking():
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
        _tracker.start()


def show_usage(*_) -> str:
    if _tracker is None:
        return "Monitoramento não iniciado."
    return _tracker.summary()


def report(*_) -> str:
    if _tracker is None:
        return "Nenhum dado disponível."
    text = _tracker.summary()
    from storage.file_store import save_text
    path = save_text(text, prefix="productivity", ext="txt")
    return f"Relatório salvo em {path}.\n\n{text}"


def daily_report(*_) -> str:
    """Gera resumo diário completo com uso de apps e o salva."""
    if _tracker is None:
        return "Monitoramento não iniciado."
    text = (
        f"# Relatório Diário — {date.today().strftime('%d/%m/%Y')}\n\n"
        + _tracker.summary()
    )
    from storage.file_store import save_text
    path = save_text(text, prefix="daily_report", ext="md")
    logger.info(f"Relatório diário salvo: {path}")
    return f"Relatório diário salvo em {path}."


def focus_start(minutes_str: str = "25", *_) -> str:
    global _pomodoro
    try:
        minutes = int(str(minutes_str).strip())
    except (ValueError, TypeError):
        minutes = 25
    _pomodoro = PomodoroTimer(minutes)
    return _pomodoro.start()


def focus_stop(*_) -> str:
    if _pomodoro is None:
        return "Nenhum timer ativo."
    return _pomodoro.stop()


def focus_status(*_) -> str:
    if _pomodoro is None:
        return "Nenhum timer ativo."
    return _pomodoro.status()
