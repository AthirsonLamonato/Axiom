"""
storage/context.py — Memória contextual de curto prazo
Mantém as últimas N interações da sessão e as injeta no prompt do LLM.
"""

import logging
from collections import deque
from typing import List, Tuple

logger = logging.getLogger(__name__)

MAX_TURNS = 10  # pares (comando, resposta) mantidos em memória

_memory: deque = deque(maxlen=MAX_TURNS)


def add(command: str, response: str) -> None:
    """Registra uma interação no contexto."""
    if command.strip() and response.strip():
        _memory.append((command.strip(), response.strip()))


def get_turns() -> List[Tuple[str, str]]:
    return list(_memory)


def build_context_prompt(new_prompt: str) -> str:
    """Retorna o prompt enriquecido com o histórico da sessão."""
    turns = get_turns()
    if not turns:
        return new_prompt
    history = "\n".join(
        f"Usuário: {cmd}\nPaçoca: {resp}"
        for cmd, resp in turns[-5:]  # máx. 5 turnos para não inflar o prompt
    )
    return (
        f"Histórico recente da conversa:\n{history}\n\n"
        f"Usuário: {new_prompt}"
    )


def clear(*_) -> str:
    _memory.clear()
    return "Contexto de conversa limpo."


def show(*_) -> str:
    if not _memory:
        return "Nenhuma interação no contexto atual."
    lines = [f"Contexto atual ({len(_memory)} interação(ões)):"]
    for i, (cmd, resp) in enumerate(_memory, 1):
        short = resp[:120] + "..." if len(resp) > 120 else resp
        lines.append(f"\n  {i}. Você:  {cmd}")
        lines.append(f"     Paçoca: {short}")
    return "\n".join(lines)
