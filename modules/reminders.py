"""
modules/reminders.py — Notificações agendadas por voz
Comandos: 'me lembra às 15h de reunião', 'me lembra em 30 minutos de fazer backup'
"""

import logging
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_reminders: Dict[int, dict] = {}
_next_id = 1
_lock = threading.Lock()
_monitor_started = False


def _ensure_monitor() -> None:
    global _monitor_started
    if _monitor_started:
        return
    _monitor_started = True
    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()


def _monitor_loop() -> None:
    while True:
        time.sleep(15)
        now = datetime.now()
        with _lock:
            to_fire = [
                (rid, r) for rid, r in _reminders.items()
                if not r["fired"] and now >= r["fire_at"]
            ]
        for rid, reminder in to_fire:
            _fire(rid, reminder["message"])


def _fire(rid: int, message: str) -> None:
    with _lock:
        if rid in _reminders:
            _reminders[rid]["fired"] = True
    try:
        from output.notifier import notify
        notify("Paçoca — Lembrete", message)
    except Exception:
        pass
    try:
        from output import overlay
        overlay.show_message(f"Lembrete: {message}")
    except Exception:
        pass
    try:
        from web.app import push_event
        push_event("reminder", f"⏰ {message}")
    except Exception:
        pass
    logger.info("Lembrete #%d disparado: %s", rid, message)
    print(f"\n[Paçoca] ⏰ Lembrete: {message}")


def _parse_fire_time(raw: str) -> Optional[datetime]:
    now = datetime.now()

    # "em X minutos"
    m = re.search(r"\bem\s+(\d+)\s*min", raw, re.I)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # "em X horas" / "em X hora"
    m = re.search(r"\bem\s+(\d+)\s*h(?:ora)?", raw, re.I)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    # "às Xh" / "as Xh30" / "às X:MM"
    m = re.search(r"\b(?:às?|as)\s+(\d{1,2})h(\d{2})?\b", raw, re.I)
    if not m:
        m = re.search(r"\b(?:às?|as)\s+(\d{1,2}):(\d{2})\b", raw, re.I)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        candidate = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    return None


def _extract_message(raw: str) -> str:
    """Remove palavras de agendamento e retorna a mensagem do lembrete."""
    text = re.sub(r"\bme\s+lembra?\s+de\s+", "", raw, flags=re.I)
    text = re.sub(r"\bme\s+lembra?\b", "", text, flags=re.I)
    text = re.sub(r"\bem\s+\d+\s*(min\w*|h(?:ora)?s?)\b", "", text, flags=re.I)
    text = re.sub(r"\b(?:às?|as)\s+\d{1,2}(?:h\d{0,2}|:\d{2})\b", "", text, flags=re.I)
    text = re.sub(r"\b(de|para)\b", "", text, flags=re.I)
    return " ".join(text.split()) or "Lembrete"


# ── Interface pública ─────────────────────────────────────────────────

def add(raw: str, *_) -> str:
    global _next_id
    fire_at = _parse_fire_time(raw)
    if fire_at is None:
        return (
            "Não entendi o horário. Exemplos:\n"
            "  'me lembra em 30 minutos de reunião'\n"
            "  'me lembra às 15h de revisar código'\n"
            "  'me lembra às 9h30 de tomar remédio'"
        )

    message = _extract_message(raw)
    with _lock:
        rid = _next_id
        _next_id += 1
        _reminders[rid] = {"fire_at": fire_at, "message": message, "fired": False}

    _ensure_monitor()

    delta_min = int((fire_at - datetime.now()).total_seconds() / 60)
    return (
        f"Lembrete #{rid} definido: '{message}' "
        f"às {fire_at.strftime('%H:%M')} (em {delta_min} min)."
    )


def list_reminders(*_) -> str:
    with _lock:
        pending = [(rid, r) for rid, r in _reminders.items() if not r["fired"]]
    if not pending:
        return "Nenhum lembrete pendente."
    lines = ["Lembretes pendentes:"]
    for rid, r in sorted(pending, key=lambda x: x[1]["fire_at"]):
        lines.append(f"  #{rid} às {r['fire_at'].strftime('%H:%M')} — {r['message']}")
    return "\n".join(lines)


def cancel(raw: str = "", *_) -> str:
    m = re.search(r"\d+", str(raw))
    if m:
        rid = int(m.group())
        with _lock:
            if rid in _reminders:
                del _reminders[rid]
                return f"Lembrete #{rid} cancelado."
        return f"Lembrete #{rid} não encontrado."
    with _lock:
        n = sum(1 for r in _reminders.values() if not r["fired"])
        _reminders.clear()
    return f"{n} lembrete(s) cancelado(s)."
