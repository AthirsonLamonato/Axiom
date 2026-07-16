"""Informacoes locais confiaveis que nao devem depender do LLM."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.config import Config


_WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)
_MONTHS = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _now() -> datetime:
    timezone_name = Config().get("calendar.timezone", "America/Sao_Paulo")
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now().astimezone()


def current_time() -> str:
    """Informa a hora do computador no fuso configurado."""
    return f"Agora são {_now():%H:%M}."


def current_date() -> str:
    """Informa a data local em português sem depender do locale do Windows."""
    now = _now()
    return (
        f"Hoje é {_WEEKDAYS[now.weekday()]}, {now.day} de "
        f"{_MONTHS[now.month - 1]} de {now.year}."
    )
