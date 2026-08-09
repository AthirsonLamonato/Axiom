"""Decisão central de risco, confirmação e autoaprovação."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Risk = Literal["low", "medium", "high", "unknown"]


@dataclass(frozen=True)
class ActionPolicy:
    risk: Risk
    requires_confirmation: bool
    external: bool = False
    can_auto_approve: bool = False


_GIT_POLICIES = {
    "status": ActionPolicy("low", False),
    "log": ActionPolicy("low", False),
    "branch": ActionPolicy("medium", False),
    "commit": ActionPolicy("medium", True, can_auto_approve=True),
    "pull": ActionPolicy("medium", True, can_auto_approve=True),
    "push": ActionPolicy("high", True),
    "reset": ActionPolicy("high", True),
}

_EXTERNAL_TOOLS = {
    "send_whatsapp_message",
    "create_calendar_event",
    "update_calendar_event",
    "delete_calendar_event",
}
_NEVER_AUTO_APPROVE = {
    "send_whatsapp_message",
    "create_calendar_event",
    "delete_calendar_event",
    "close_application",
}


def resolve(
    name: str,
    args: dict | None = None,
    *,
    base_risk: Risk = "unknown",
    base_confirmation: bool = False,
) -> ActionPolicy:
    """Resolve exceções dinâmicas sem espalhá-las pelo orquestrador."""
    args = args or {}
    if name == "git_operation":
        return _GIT_POLICIES.get(str(args.get("operation", "")).lower(), ActionPolicy(base_risk, base_confirmation))

    external = name in _EXTERNAL_TOOLS or bool(args.get("attendees"))
    risk = "high" if external and base_risk != "high" else base_risk
    confirm = base_confirmation or external
    auto = risk == "medium" and confirm and name not in _NEVER_AUTO_APPROVE and not external
    return ActionPolicy(risk, confirm, external, auto)


def classify_text(command: str) -> ActionPolicy:
    """Política conservadora para rotas diretas antes do parsing estruturado."""
    text = (command or "").strip().lower()
    external = bool(re.search(r"(whatsapp|e-?mail|mensagem\s+(?:para|pra|ao|à)|convid|@)", text))
    destructive = bool(re.search(r"(apaga|deleta|exclui|fecha\s+(?:o|a|tudo)|git\s+(?:push|reset)|format)", text))
    medium = bool(re.search(r"(git\s+(?:commit|pull)|cria.*evento|adiciona.*evento|remarca|altera.*evento|esquece)", text))
    if external or destructive:
        return ActionPolicy("high", True, external=external)
    if medium:
        return ActionPolicy("medium", True, can_auto_approve=True)
    return ActionPolicy("low", False)
