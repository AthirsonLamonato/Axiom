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


def _is_eligible(tool: str, args: dict | None = None) -> bool:
    """Só ações explicitamente elegíveis pela política central aprendem."""
    try:
        from modules.tools import get_policy
        return get_policy(tool, args).can_auto_approve
    except Exception:
        return False


def _trust_key(tool: str, args: dict | None = None) -> str:
    operation = str((args or {}).get("operation", "")).strip().lower()
    return f"{tool}:{operation}" if operation else tool


def _policy_subject(key: str) -> tuple[str, dict]:
    if key.startswith("git_operation:"):
        return "git_operation", {"operation": key.split(":", 1)[1]}
    return key, {}


def auto_approve(tool: str, args: dict | None = None) -> bool:
    """True se a ação já é confiável e pode pular a confirmação."""
    if not _is_enabled() or not _is_eligible(tool, args):
        return False
    try:
        from storage.memory import get_trust
        streak = get_trust(_trust_key(tool, args)).get("streak", 0)
    except Exception:
        return False
    return streak >= _threshold()


def record(tool: str, approved: bool, args: dict | None = None) -> None:
    """Registra a decisão de confirmação (só para ações elegíveis)."""
    if not _is_enabled() or not _is_eligible(tool, args):
        return
    try:
        from storage.memory import record_confirmation
        record_confirmation(_trust_key(tool, args), approved)
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
        tool, args = _policy_subject(r["tool"])
        if not _is_eligible(tool, args):
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
