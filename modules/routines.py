"""
modules/routines.py — Automação de rotinas configuráveis com suporte a condições
"""

import json
import logging
import re
import threading
import time
from datetime import datetime, date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_scheduler_running = False
_scheduler_thread: "threading.Thread | None" = None
_last_run_date: dict = {}   # nome da rotina -> date() do último disparo automático
_SCHEDULER_INTERVAL = 60    # segundos entre verificações
_FIRE_WINDOW = timedelta(minutes=2)  # tolerância p/ não perder o minuto-alvo por drift do loop
SCHEDULE_STATE_PATH = Path("data/routine_schedule.json")
_schedule_state_loaded = False

ACTION_SPECS = {
    "open_app": {"label": "Abrir aplicativo", "argument": "target"},
    "close_app": {"label": "Fechar aplicativo", "argument": "target"},
    "set_volume": {"label": "Definir volume", "argument": "target"},
    "notify": {"label": "Notificação local", "argument": "message"},
    "save_transcriptions": {"label": "Salvar transcrições", "argument": None},
    "close_overlay": {"label": "Fechar overlay", "argument": None},
    "daily_report": {"label": "Relatório diário", "argument": None},
    "focus": {"label": "Iniciar foco", "argument": "target"},
}


def build_step(action: str, value: str = "") -> dict:
    """Valida e normaliza uma etapa criada por interface externa."""
    action = action.strip()
    if action not in ACTION_SPECS:
        raise ValueError("Ação de rotina não permitida.")
    value = value.strip()
    if len(value) > 200:
        raise ValueError("Parâmetro da rotina excede 200 caracteres.")
    argument = ACTION_SPECS[action]["argument"]
    if argument and not value:
        raise ValueError("Esta ação exige um parâmetro.")
    if action == "set_volume":
        try:
            volume = int(value)
        except ValueError as exc:
            raise ValueError("Volume deve ser um número entre 0 e 100.") from exc
        if not 0 <= volume <= 100:
            raise ValueError("Volume deve ser um número entre 0 e 100.")
        value = str(volume)
    if action == "focus":
        try:
            minutes = int(value)
        except ValueError as exc:
            raise ValueError("Foco deve ter entre 1 e 180 minutos.") from exc
        if not 1 <= minutes <= 180:
            raise ValueError("Foco deve ter entre 1 e 180 minutos.")
        value = str(minutes)
    return {"action": action, **({argument: value} if argument else {})}


def validate_routine_name(name: str) -> str:
    name = name.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{1,40}", name):
        raise ValueError("Nome deve usar apenas letras minúsculas, números e _. ")
    return name


def _load_schedule_state() -> None:
    global _schedule_state_loaded
    if _schedule_state_loaded:
        return
    _schedule_state_loaded = True
    if not SCHEDULE_STATE_PATH.exists():
        return
    try:
        payload = json.loads(SCHEDULE_STATE_PATH.read_text(encoding="utf-8"))
        for name, value in payload.get("last_run", {}).items():
            _last_run_date[str(name)] = date.fromisoformat(str(value))
    except Exception as exc:
        logger.error("Estado do agendador inválido; reiniciando vazio: %s", exc)
        _last_run_date.clear()


def _save_schedule_state() -> None:
    SCHEDULE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "last_run": {k: v.isoformat() for k, v in _last_run_date.items()}}
    temp = SCHEDULE_STATE_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(SCHEDULE_STATE_PATH)


def _get_config():
    from core.config import Config
    return Config()


def work_mode(*_) -> str:
    return run("work_mode")


def focus_mode(*_) -> str:
    from modules.system_control import mute
    mute()
    return "Modo foco ativado. Notificações silenciadas."


def end_of_day(*_) -> str:
    return run("end_of_day")


def run(routine_name: str, *_) -> str:
    config = _get_config()
    routines = config.get("routines", {})

    if routine_name not in routines:
        available = ", ".join(routines.keys()) or "nenhuma"
        return f"Rotina '{routine_name}' não encontrada. Disponíveis: {available}"

    routine = routines[routine_name]

    # Verifica condição da rotina (ex: só executar em dias úteis)
    condition = routine.get("condition")
    if condition and not _evaluate_condition(condition):
        return f"Rotina '{routine_name}' ignorada: condição '{condition}' não satisfeita."

    steps = routine.get("steps", [])
    results = []

    for step in steps:
        # Condição por etapa
        step_cond = step.get("condition")
        if step_cond and not _evaluate_condition(step_cond):
            logger.debug(f"Etapa ignorada por condição: {step_cond}")
            continue

        result = _execute_step(
            step.get("action"),
            step.get("target", ""),
            step.get("message", ""),
        )
        if result:
            results.append(result)
        time.sleep(0.3)

    label = routine.get("name", routine_name)
    return f"Rotina '{label}' executada."


def _evaluate_condition(condition: str, now: "datetime | None" = None) -> bool:
    """
    Avalia condições simples:
      weekday       → seg–sex
      weekend       → sáb–dom
      morning       → 6h–12h
      afternoon     → 12h–18h
      evening       → 18h–24h
    """
    now = now or datetime.now()
    cond = condition.strip().lower()

    if cond == "weekday":
        return now.weekday() < 5
    if cond == "weekend":
        return now.weekday() >= 5
    if cond == "morning":
        return 6 <= now.hour < 12
    if cond == "afternoon":
        return 12 <= now.hour < 18
    if cond == "evening":
        return 18 <= now.hour < 24

    logger.warning(f"Condição desconhecida: {condition!r}")
    return False


def _execute_step(action: str, target: str = "", message: str = "") -> "str | None":
    if action not in ACTION_SPECS:
        logger.warning("Ação de rotina bloqueada: %r", action)
        return None
    try:
        if action == "open_app":
            from modules.system_control import open_app
            return open_app(target)
        elif action == "close_app":
            from modules.system_control import close_app
            return close_app(target)
        elif action == "set_volume":
            from modules.system_control import set_volume
            return set_volume(target)
        elif action == "notify":
            from output.notifier import notify
            notify("Paçoca", message)
            return message
        elif action == "save_transcriptions":
            from storage.file_store import save_all_pending
            return save_all_pending()
        elif action == "close_overlay":
            from output.overlay import hide
            hide()
            return "Overlay fechado."
        elif action == "daily_report":
            from modules.productivity import daily_report
            return daily_report()
        elif action == "focus":
            from modules.productivity import focus_start
            return focus_start(target or "25")
        else:
            logger.warning(f"Ação desconhecida: {action!r}")
            return None
    except Exception as e:
        logger.error(f"Erro na etapa '{action}': {e}")
        return f"Erro em '{action}': {e}"


# ── Agendamento automático ─────────────────────────────────────────────
# Rotinas podem declarar um bloco `schedule: {time: "HH:MM", days: <condição>}`
# no config.yaml para serem disparadas sozinhas, sem comando do usuário.

def _matches_schedule(schedule: dict, now: datetime) -> bool:
    sched_time = str(schedule.get("time", "")).strip()
    if not sched_time:
        return False
    try:
        hh, mm = (int(p) for p in sched_time.split(":"))
    except ValueError:
        return False
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if not (target <= now < target + _FIRE_WINDOW):
        return False
    days = schedule.get("days", "daily")
    if days == "daily":
        return True
    return _evaluate_condition(str(days), now)


def _scheduler_loop() -> None:
    global _scheduler_running
    _load_schedule_state()
    while _scheduler_running:
        try:
            now = datetime.now()
            config = _get_config()
            routines = config.get("routines", {}) or {}
            for name, routine in routines.items():
                schedule = routine.get("schedule") if isinstance(routine, dict) else None
                if not schedule:
                    continue
                if _last_run_date.get(name) == date.today():
                    continue
                if _matches_schedule(schedule, now):
                    logger.info("Rotina '%s' disparada automaticamente pelo agendador.", name)
                    _last_run_date[name] = date.today()
                    _save_schedule_state()
                    run(name)
        except Exception as e:
            logger.error("Erro no agendador de rotinas: %s", e)
        time.sleep(_SCHEDULER_INTERVAL)


def start_scheduler() -> None:
    """Inicia a thread de verificação de rotinas agendadas (idempotente)."""
    global _scheduler_running, _scheduler_thread
    if _scheduler_running:
        return
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()


def stop_scheduler() -> None:
    global _scheduler_running
    _scheduler_running = False
