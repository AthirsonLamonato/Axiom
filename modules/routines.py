"""
modules/routines.py — Automação de rotinas configuráveis
Executa sequências de ações definidas no config.yaml.
"""

import logging
import time

logger = logging.getLogger(__name__)


def _get_config():
    from core.config import Config
    return Config()


def work_mode(*_) -> str:
    return run("work_mode")


def focus_mode(*_) -> str:
    """Ativa modo foco: silencia e bloqueia distrações."""
    from modules.system_control import mute
    mute()
    return "Modo foco ativado. Notificações silenciadas."


def end_of_day(*_) -> str:
    return run("end_of_day")


def run(routine_name: str, *_) -> str:
    """Executa uma rotina pelo nome definido em config.yaml."""
    config = _get_config()
    routines = config.get("routines", {})

    if routine_name not in routines:
        available = ", ".join(routines.keys())
        return f"Rotina '{routine_name}' não encontrada. Disponíveis: {available}"

    routine = routines[routine_name]
    steps = routine.get("steps", [])
    results = []

    for step in steps:
        action = step.get("action")
        target = step.get("target", "")
        message = step.get("message", "")

        result = _execute_step(action, target, message)
        if result:
            results.append(result)
        time.sleep(0.5)  # pequena pausa entre etapas

    label = routine.get("name", routine_name)
    return f"Rotina '{label}' executada."


def _execute_step(action: str, target: str = "", message: str = "") -> str:
    """Executa uma etapa individual da rotina."""
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
            notify("Axiom", message)
            return message

        elif action == "save_transcriptions":
            from storage.file_store import save_all_pending
            return save_all_pending()

        elif action == "close_overlay":
            from output.overlay import hide
            hide()
            return "Overlay fechado."

        else:
            logger.warning(f"Ação de rotina desconhecida: {action}")
            return None

    except Exception as e:
        logger.error(f"Erro na etapa '{action}': {e}")
        return f"Erro em '{action}': {e}"
