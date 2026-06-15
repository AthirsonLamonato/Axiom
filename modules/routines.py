"""
modules/routines.py — Automação de rotinas configuráveis com suporte a condições
"""

import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


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


def _evaluate_condition(condition: str) -> bool:
    """
    Avalia condições simples:
      weekday       → seg–sex
      weekend       → sáb–dom
      morning       → 6h–12h
      afternoon     → 12h–18h
      evening       → 18h–24h
    """
    now = datetime.now()
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
    return True  # condição desconhecida → não bloqueia


def _execute_step(action: str, target: str = "", message: str = "") -> "str | None":
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
