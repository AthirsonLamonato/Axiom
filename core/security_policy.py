"""Políticas de ferramentas por perfil de uso.

A política é conservadora, mas retrocompatível: quando não existe configuração
específica, todas as ferramentas continuam disponíveis e as confirmações do
registro central permanecem obrigatórias.
"""

from __future__ import annotations

from typing import Any

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _config_data() -> dict[str, Any]:
    try:
        from core.config import Config
        return Config().all()
    except Exception:
        return {}


def active_profile() -> str:
    data = _config_data()
    return str(data.get("profile", {}).get("active", "work"))


def check_tool(tool: str, risk: str) -> tuple[bool, str]:
    """Retorna se a ferramenta é permitida pelo perfil ativo."""
    data = _config_data()
    profile = active_profile()
    policies = data.get("security", {}).get("profile_policies", {})
    policy = policies.get(profile) or policies.get("default") or {}
    if not isinstance(policy, dict):
        return True, ""

    denied = policy.get("denied_tools", []) or []
    if tool in denied:
        return False, f"A ferramenta '{tool}' está bloqueada pelo perfil '{profile}'."

    allowed = policy.get("allowed_tools", []) or []
    if allowed and tool not in allowed:
        return False, f"A ferramenta '{tool}' não está autorizada no perfil '{profile}'."

    max_risk = str(policy.get("max_risk", "high"))
    if _RISK_ORDER.get(risk, 2) > _RISK_ORDER.get(max_risk, 2):
        return False, (
            f"A ferramenta '{tool}' excede o risco máximo '{max_risk}' "
            f"do perfil '{profile}'."
        )
    return True, ""


def describe() -> dict[str, Any]:
    data = _config_data()
    profile = active_profile()
    policies = data.get("security", {}).get("profile_policies", {})
    policy = policies.get(profile) or policies.get("default") or {}
    return {"profile": profile, "policy": policy if isinstance(policy, dict) else {}}
