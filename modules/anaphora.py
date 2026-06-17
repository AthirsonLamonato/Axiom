"""
modules/anaphora.py — Resolução de seguimento e anáfora

Reescreve comandos que só fazem sentido com o turno anterior, usando o
histórico de diálogo (storage/context). Exemplos:

  "toca de novo"        → repete o último comando
  "fecha ele"           → "fecha <último app aberto>"
  "e amanhã?"           → "agenda amanhã"   (após "agenda hoje")
  "e em Recife?"        → "clima em Recife" (após perguntar o clima)
  "aumenta mais"        → repete o último ajuste de volume/brilho

É conservador de propósito: se não tem certeza, devolve o comando original
intacto — nunca "adivinha" a ponto de mudar a intenção.
"""

import logging
import re

logger = logging.getLogger(__name__)

# "faça de novo" / "toca de novo" / "repete" → reexecuta o último comando
_REPEAT = re.compile(
    r"\b(de novo|denovo|novamente|outra vez|mais uma vez)\b", re.IGNORECASE,
)
_REPEAT_BARE = re.compile(
    r"^(repete|repetir|repita|isso|de novo|denovo|novamente)\s*$", re.IGNORECASE,
)

# "fecha ele/isso" → fecha o último alvo aberto
_CLOSE_PRONOUN = re.compile(
    r"^(fecha|fechar|para|parar|encerra|encerrar)\s+"
    r"(ele|ela|isso|isto|esse|essa|aquilo|o mesmo|a mesma)\b",
    re.IGNORECASE,
)
_OPENED = re.compile(r"^(?:abr[ae]|abrir|abra)\s+(.+)", re.IGNORECASE)

# "e amanhã?" / "e em Recife?" → reaproveita a intenção anterior com novo slot
_ELLIPSIS = re.compile(r"^e\s+(.+?)\s*\??$", re.IGNORECASE)

# Ajuste incremental de volume/brilho
_INCREMENT = re.compile(
    r"^(mais|menos|aumenta mais|diminui mais|um pouco mais|mais um pouco|"
    r"um pouco menos)\s*$",
    re.IGNORECASE,
)
_ADJUST_CTX = re.compile(r"\b(volume|brilho|som|aumenta|diminui|sobe|baixa)\b", re.IGNORECASE)

_DAY_WORDS = {"hoje", "amanhã", "amanha", "amanhã?", "depois de amanhã"}


def _enabled() -> bool:
    try:
        from core.config import Config
        return bool(Config().get("anaphora.enabled", True))
    except Exception:
        return True


def _last_command() -> str:
    try:
        from storage.context import get_turns
        turns = get_turns()
        return turns[-1][0] if turns else ""
    except Exception:
        return ""


def resolve(command: str) -> str:
    """Reescreve `command` se for um seguimento; senão devolve igual."""
    if not _enabled() or not command or not command.strip():
        return command

    cmd = command.strip()
    last = _last_command()
    if not last:
        return command

    # 1. Repetição → reexecuta o último comando literalmente
    if (_REPEAT.search(cmd) or _REPEAT_BARE.match(cmd)) and len(cmd.split()) <= 5:
        logger.debug("anáfora: repetição → %r", last)
        return last

    # 2. "fecha ele/isso" → fecha o último app aberto
    m = _CLOSE_PRONOUN.match(cmd)
    if m:
        opened = _OPENED.match(last)
        if opened:
            target = opened.group(1).strip()
            return f"{m.group(1)} {target}"

    # 3. Ajuste incremental ("mais"/"menos") herdando volume/brilho do anterior
    if _INCREMENT.match(cmd) and _ADJUST_CTX.search(last):
        logger.debug("anáfora: incremento herda %r", last)
        return last

    # 4. Elipse "e <tail>?" → reaproveita a intenção anterior
    m = _ELLIPSIS.match(cmd)
    if m:
        tail = m.group(1).strip().rstrip("?").strip()
        rewritten = _apply_ellipsis(last, tail)
        if rewritten:
            logger.debug("anáfora: elipse %r + %r → %r", last, tail, rewritten)
            return rewritten

    return command


def _apply_ellipsis(last: str, tail: str) -> str:
    """Aplica o novo slot `tail` sobre a intenção do comando anterior."""
    low = last.lower()
    tail_low = tail.lower()

    # Agenda: "agenda hoje" + "e amanhã" → "agenda amanhã"
    if re.search(r"\b(agenda|tenho|compromisso|evento)\b", low) and tail_low in _DAY_WORDS:
        return f"agenda {tail}"

    # Clima: "como está o tempo" + "e em Recife" / "e amanhã"
    if re.search(r"\b(clima|tempo|previs[ãa]o)\b", low):
        place = re.sub(r"^(em|no|na|para|pra)\s+", "", tail_low).strip()
        if place and place not in _DAY_WORDS:
            return f"como está o tempo em {place}"

    # Genérico: troca o último token do comando anterior pelo novo slot,
    # mas só quando o tail parece um valor simples (1–2 palavras).
    if len(tail.split()) <= 2 and len(last.split()) >= 2:
        tokens = last.split()
        return " ".join(tokens[:-1] + [tail])

    return ""
