"""Política fail-closed para comunicações externas reais.

O modo padrão é simulação. Uma ação real só pode ocorrer quando três travas
independentes estão ativas: modo ``live``, flag de configuração e uma frase
exata em variável de ambiente. Confirmação por ação continua obrigatória no
orquestrador; esta política é uma barreira adicional no executor final.
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Any

LIVE_ENV_VAR = "PACOCA_ALLOW_REAL_EXTERNAL_ACTIONS"
LIVE_ENV_TOKEN = "CONFIRM_REAL_EXTERNAL_ACTIONS"


def live_enabled(config: Any | None = None) -> bool:
    """True somente com as três travas explícitas habilitadas."""
    if config is None:
        from core.config import Config

        config = Config()

    mode = str(config.get("external_actions.mode", "simulate")).strip().lower()
    enabled = config.get("external_actions.live_enabled", False) is True
    env_value = os.environ.get(LIVE_ENV_VAR, "")
    env_ok = hmac.compare_digest(env_value, LIVE_ENV_TOKEN)
    return mode == "live" and enabled and env_ok


def mask_recipient(recipient: str) -> str:
    """Mascara telefone/e-mail para respostas e logs de auditoria."""
    value = str(recipient or "").strip()
    parts = [part.strip() for part in re.split(r"[,;]", value) if part.strip()]
    if len(parts) > 1:
        return ", ".join(mask_recipient(part) for part in parts)
    if "@" in value:
        local, domain = value.split("@", 1)
        visible = local[:1] if local else "*"
        return f"{visible}***@{domain}"

    digits = re.sub(r"\D", "", value)
    if not digits:
        return "destinatário oculto"
    return f"***{digits[-4:]}"


def simulation_result(channel: str, recipient: str) -> str:
    """Resposta inequívoca: nenhuma integração de envio foi chamada."""
    return (
        f"[SIMULAÇÃO] {channel} preparado para {mask_recipient(recipient)}. "
        "Nada foi enviado e nenhuma integração externa de envio foi chamada."
    )
