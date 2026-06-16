"""
core/telemetry.py — Observabilidade por comando

Registra por comando: rota, ferramenta, provedor, latência, tokens, sucesso, fallback.
Exposto via dashboard (GET /api/metrics) — sem conteúdo sensível.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 500
_lock = threading.Lock()

@dataclass
class CommandMetric:
    ts: float              = field(default_factory=time.time)
    command_hash: str      = ""   # hash curto do comando — sem texto real
    route: str             = ""
    tool: str              = ""
    provider: str          = ""
    latency_s: float       = 0.0
    prompt_tokens: int     = 0
    completion_tokens: int = 0
    success: bool          = True
    fallback_used: bool    = False
    error: str             = ""

@dataclass
class LLMCallMetric:
    ts: float         = field(default_factory=time.time)
    provider: str     = ""
    latency_s: float  = 0.0
    prompt_tokens: int     = 0
    completion_tokens: int = 0

_command_log: deque[CommandMetric] = deque(maxlen=_MAX_ENTRIES)
_llm_log:     deque[LLMCallMetric] = deque(maxlen=_MAX_ENTRIES)

# ── Escrita ───────────────────────────────────────────────────────────

def record_command(
    command: str,
    route: str = "",
    tool: str = "",
    provider: str = "",
    latency_s: float = 0.0,
    success: bool = True,
    fallback_used: bool = False,
    error: str = "",
) -> None:
    import hashlib
    h = hashlib.sha1(command.encode()).hexdigest()[:8]
    m = CommandMetric(
        command_hash=h,
        route=route,
        tool=tool,
        provider=provider,
        latency_s=latency_s,
        success=success,
        fallback_used=fallback_used,
        error=error,
    )
    with _lock:
        _command_log.append(m)


def record_llm_call(
    provider: str,
    latency_s: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    m = LLMCallMetric(
        provider=provider,
        latency_s=latency_s,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    with _lock:
        _llm_log.append(m)


# ── Leitura / agregação ───────────────────────────────────────────────

def get_summary(last_n: int = 100) -> dict:
    """Retorna estatísticas agregadas sem conteúdo sensível."""
    with _lock:
        cmds = list(_command_log)[-last_n:]
        llms = list(_llm_log)[-last_n:]

    total = len(cmds)
    if total == 0:
        return {"total_commands": 0}

    success_rate = sum(1 for c in cmds if c.success) / total
    avg_latency  = sum(c.latency_s for c in cmds) / total

    providers: dict[str, int] = {}
    fallbacks = 0
    for c in cmds:
        providers[c.provider or "unknown"] = providers.get(c.provider or "unknown", 0) + 1
        if c.fallback_used:
            fallbacks += 1

    llm_by_provider: dict[str, dict] = {}
    for l in llms:
        p = l.provider
        if p not in llm_by_provider:
            llm_by_provider[p] = {"calls": 0, "total_tokens": 0, "total_latency_ms": 0.0}
        llm_by_provider[p]["calls"] += 1
        llm_by_provider[p]["total_tokens"] += l.prompt_tokens + l.completion_tokens
        llm_by_provider[p]["total_latency_ms"] += l.latency_s * 1000

    # Compute avg from accumulated totals
    for p_stats in llm_by_provider.values():
        total_ms = p_stats.pop("total_latency_ms", 0.0)
        n = p_stats["calls"]
        p_stats["avg_latency_ms"] = round(total_ms / n, 1) if n else 0.0

    return {
        "total_commands": total,
        "success_rate": round(success_rate, 3),
        "avg_latency_ms": round(avg_latency * 1000, 1),
        "fallback_rate": round(fallbacks / total, 3),
        "providers": providers,
        "llm": llm_by_provider,
    }


def get_recent(n: int = 20) -> list[dict]:
    """Retorna os N comandos mais recentes sem texto original."""
    with _lock:
        entries = list(_command_log)[-n:]
    return [
        {
            "ts": round(e.ts, 2),
            "route": e.route,
            "tool": e.tool,
            "provider": e.provider,
            "latency_ms": round(e.latency_s * 1000, 1),
            "success": e.success,
            "fallback": e.fallback_used,
            "error": e.error[:80] if e.error else "",
        }
        for e in reversed(entries)
    ]
