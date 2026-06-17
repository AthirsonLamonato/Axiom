"""
modules/briefing.py — Briefing diário proativo
Compõe clima + agenda + lembretes pendentes + uso do dia anterior.
Dispara automaticamente 1x por dia no horário configurado (briefing.time),
sem precisar de comando do usuário, além de poder ser pedido por voz/texto.
"""

import logging
import threading
import time
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

_running = False
_thread: "threading.Thread | None" = None
_last_fired_date: "date | None" = None
_CHECK_INTERVAL = 60  # segundos
_FIRE_WINDOW = timedelta(minutes=2)  # tolerância p/ não perder o minuto-alvo por drift do loop


def _is_due(sched_time: str, now: datetime) -> bool:
    """True se `now` está na janela [horário-alvo, horário-alvo + _FIRE_WINDOW)."""
    try:
        hh, mm = (int(p) for p in sched_time.split(":"))
    except ValueError:
        return False
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return target <= now < target + _FIRE_WINDOW


def _get_config():
    from core.config import Config
    return Config()


def generate(*_) -> str:
    """Monta o briefing do dia: clima, agenda, lembretes e uso de ontem."""
    parts = [f"☀️ Bom dia! Briefing de {date.today().strftime('%d/%m/%Y')}:"]

    try:
        from modules.weather import get_weather
        parts.append(get_weather(""))
    except Exception as e:
        logger.debug("Briefing: clima indisponível: %s", e)

    try:
        from modules.calendar_integration import get_today_events
        parts.append(get_today_events())
    except Exception as e:
        logger.debug("Briefing: agenda indisponível: %s", e)

    try:
        from modules.reminders import list_reminders
        parts.append(list_reminders())
    except Exception as e:
        logger.debug("Briefing: lembretes indisponíveis: %s", e)

    try:
        from modules.productivity import show_usage
        parts.append(show_usage())
    except Exception as e:
        logger.debug("Briefing: produtividade indisponível: %s", e)

    return "\n\n".join(parts)


def _fire_briefing() -> None:
    text = generate()
    try:
        from output.notifier import notify
        notify("Paçoca — Bom dia", "Seu briefing do dia está pronto.")
    except Exception:
        pass
    try:
        from output import overlay
        overlay.show_message("Briefing do dia gerado. Confira o histórico.", duration_ms=8000)
    except Exception:
        pass
    try:
        from web.app import push_event
        push_event("info", "☀️ Briefing diário gerado")
    except Exception:
        pass
    logger.info("Briefing diário disparado automaticamente.")
    print(f"\n[Paçoca] {text}\n")


def _scheduler_loop() -> None:
    global _last_fired_date
    while _running:
        try:
            config = _get_config()
            if config.get("briefing.enabled", True):
                sched_time = str(config.get("briefing.time", "08:00")).strip()
                now = datetime.now()
                if _last_fired_date != date.today() and _is_due(sched_time, now):
                    _last_fired_date = date.today()
                    _fire_briefing()
        except Exception as e:
            logger.error("Erro no agendador de briefing: %s", e)
        time.sleep(_CHECK_INTERVAL)


def start_scheduler() -> None:
    """Inicia a verificação periódica do horário de briefing (idempotente)."""
    global _running, _thread
    if _running:
        return
    _running = True
    _thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _thread.start()


def stop_scheduler() -> None:
    global _running
    _running = False
