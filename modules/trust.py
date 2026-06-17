"""
modules/trust.py — Aprendizado de confiança para confirmações

Reduz a "fadiga de confirmação": depois que o usuário aprova a MESMA ação de
risco MÉDIO N vezes seguidas, o Paçoca deixa de perguntar e executa direto.

Regras de segurança (invioláveis):
  - Só ações de risco "medium" são elegíveis. Risco "high" (ex: enviar
    WhatsApp, apagar evento) SEMPRE pede confirmação, não importa o histórico.
  - Uma única negação zera a sequência (streak) e volta a perguntar.
  - Tudo é desativável via config (trust.enabled).
"""

import logging

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 3   # aprovações consecutivas para passar a confiar


def _config():
    from core.config import Config
    return Config()


def _is_enabled() -> bool:
    try:
        return bool(_config().get("trust.enabled", True))
    except Exception:
        return True


def _threshold() -> int:
    try:
        return int(_config().get("trust.threshold", _DEFAULT_THRESHOLD))
    except Exception:
        return _DEFAULT_THRESHOLD


def _is_eligible(tool: str) -> bool:
    """Só ações de risco médio aprendem confiança — alto nunca."""
    try:
        from modules.tools import get_risk
        return get_risk(tool) == "medium"
    except Exception:
        return False


def auto_approve(tool: str) -> bool:
    """True se a ação já é confiável e pode pular a confirmação."""
    if not _is_enabled() or not _is_eligible(tool):
        return False
    try:
        from storage.memory import get_trust
        streak = get_trust(tool).get("streak", 0)
    except Exception:
        return False
    return streak >= _threshold()


def record(tool: str, approved: bool) -> None:
    """Registra a decisão de confirmação (só para ações elegíveis)."""
    if not _is_enabled() or not _is_eligible(tool):
        return
    try:
        from storage.memory import record_confirmation
        record_confirmation(tool, approved)
    except Exception as e:
        logger.debug("Falha ao registrar confiança de '%s': %s", tool, e)


# ── Comandos de voz/texto ──────────────────────────────────────────────

def status(*_) -> str:
    """Mostra o que o Paçoca já confia e o progresso das demais ações."""
    try:
        from storage.memory import get_all_trust
        rows = get_all_trust()
    except Exception as e:
        return f"Erro ao consultar confiança: {e}"

    if not rows:
        return "Ainda não aprendi confiança para nenhuma ação. Confirmo tudo normalmente."

    threshold = _threshold()
    trusted, learning = [], []
    for r in rows:
        if not _is_eligible(r["tool"]):
            continue
        if r["streak"] >= threshold:
            trusted.append(f"  ✓ {r['tool']} (não pergunto mais)")
        elif r["streak"] > 0:
            learning.append(f"  … {r['tool']} ({r['streak']}/{threshold} aprovações)")

    if not trusted and not learning:
        return "Ainda não aprendi confiança para nenhuma ação. Confirmo tudo normalmente."

    lines = ["Confiança aprendida (só ações de risco médio):"]
    lines.extend(trusted)
    lines.extend(learning)
    return "\n".join(lines)


def reset(*_) -> str:
    """Zera toda a confiança aprendida — volto a confirmar tudo."""
    try:
        from storage.memory import reset_trust
        reset_trust()
        return "Confiança zerada. Vou voltar a confirmar todas as ações."
    except Exception as e:
        return f"Erro ao resetar confiança: {e}"
