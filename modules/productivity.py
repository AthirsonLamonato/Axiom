"""
modules/productivity.py — Monitoramento de uso e timer de foco (Pomodoro)
"""

import logging
import json
import time
import threading
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_tracker: "UsageTracker | None" = None
_pomodoro: "PomodoroTimer | None" = None
POMODORO_STATE_PATH = Path("data/pomodoro.json")


def _save_pomodoro(timer: "PomodoroTimer") -> None:
    POMODORO_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = POMODORO_STATE_PATH.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps({"minutes": timer.minutes, "end_at": timer._end_at.isoformat()}),
        encoding="utf-8",
    )
    temp.replace(POMODORO_STATE_PATH)


def _clear_pomodoro_state() -> None:
    POMODORO_STATE_PATH.unlink(missing_ok=True)


def _restore_pomodoro() -> "PomodoroTimer | None":
    if not POMODORO_STATE_PATH.exists():
        return None
    try:
        payload = json.loads(POMODORO_STATE_PATH.read_text(encoding="utf-8"))
        end_at = datetime.fromisoformat(payload["end_at"])
        if end_at <= datetime.now():
            _clear_pomodoro_state()
            return None
        timer = PomodoroTimer(int(payload["minutes"]), end_at=end_at)
        timer.start()
        return timer
    except Exception as e:
        logger.error("Estado do Pomodoro inválido: %s", e)
        _clear_pomodoro_state()
        return None


# ── Rastreamento de uso ────────────────────────────────────────────────

class UsageTracker:
    def __init__(self, interval: int = 10):
        self.interval = interval
        self._usage: dict = defaultdict(float)
        self._running = False
        self._thread: "threading.Thread | None" = None
        self._date = date.today()
        self._last_break = time.monotonic()
        self._break_notified = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("UsageTracker iniciado")

    def stop(self):
        self._running = False

    def take_break(self) -> None:
        self._last_break = time.monotonic()
        self._break_notified = False

    def _check_break_suggestion(self):
        try:
            from core.config import Config
            threshold_min = float(Config().get("productivity.break_after_min", 90))
        except Exception:
            threshold_min = 90
        if threshold_min <= 0 or self._break_notified:
            return
        elapsed_min = (time.monotonic() - self._last_break) / 60
        if elapsed_min < threshold_min:
            return
        self._break_notified = True
        message = f"Você está sem pausa há {int(elapsed_min)} minutos. Que tal descansar um pouco?"
        try:
            from output.notifier import notify
            notify("Paçoca", message)
        except Exception:
            pass
        try:
            from output import overlay
            overlay.show_message(message, duration_ms=8000)
        except Exception:
            pass
        try:
            from web.app import push_event
            push_event("info", f"🧘 {message}")
        except Exception:
            pass
        logger.info("Sugestão de pausa disparada (%.0f min sem pausa).", elapsed_min)

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
            self._check_break_suggestion()
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
    def __init__(self, minutes: int, on_finish=None, end_at: datetime | None = None):
        self.minutes = minutes
        self.on_finish = on_finish
        self._thread: "threading.Thread | None" = None
        self._running = False
        self._started_at: "datetime | None" = None
        self._end_at = end_at

    def start(self) -> str:
        if self._running:
            elapsed = int((datetime.now() - self._started_at).total_seconds() // 60)
            remaining = self.minutes - elapsed
            return f"Timer já ativo: {remaining} minutos restantes."
        self._running = True
        now = datetime.now()
        self._end_at = self._end_at or (now + timedelta(minutes=self.minutes))
        self._started_at = self._end_at - timedelta(minutes=self.minutes)
        _save_pomodoro(self)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return f"Timer de foco iniciado: {self.minutes} minutos. Bom trabalho!"

    def stop(self) -> str:
        if not self._running:
            return "Nenhum timer ativo."
        self._running = False
        _clear_pomodoro_state()
        return "Timer cancelado."

    def status(self) -> str:
        if not self._running:
            return "Nenhum timer ativo."
        remaining = int((self._end_at - datetime.now()).total_seconds())
        if remaining <= 0:
            return "Timer concluído."
        m, s = divmod(remaining, 60)
        return f"Timer de foco: {m:02d}:{s:02d} restantes."

    def _run(self):
        while self._running:
            remaining = (self._end_at - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(1, remaining))
        if not self._running:
            return
        self._running = False
        _clear_pomodoro_state()
        from output.notifier import notify
        notify("Paçoca — Pomodoro", f"Sessão de {self.minutes} minutos concluída! Descanse.")
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


def take_break(*_) -> str:
    if _tracker is None:
        return "Monitoramento não iniciado."
    _tracker.take_break()
    return "Pausa registrada. Aviso o próximo lembrete de descanso."


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
    if _pomodoro is not None and _pomodoro._running:
        return _pomodoro.start()
    _pomodoro = PomodoroTimer(minutes)
    return _pomodoro.start()


def focus_start_hours(hours_str: str = "1", *_) -> str:
    try:
        minutes = int(str(hours_str).strip()) * 60
    except (ValueError, TypeError):
        minutes = 60
    return focus_start(str(minutes))


def focus_stop(*_) -> str:
    global _pomodoro
    if _pomodoro is None:
        _pomodoro = _restore_pomodoro()
    if _pomodoro is None:
        return "Nenhum timer ativo."
    return _pomodoro.stop()


def focus_status(*_) -> str:
    global _pomodoro
    if _pomodoro is None:
        _pomodoro = _restore_pomodoro()
    if _pomodoro is None:
        return "Nenhum timer ativo."
    return _pomodoro.status()
