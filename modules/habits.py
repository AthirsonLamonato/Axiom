"""
modules/habits.py — Detector de hábitos e sugestão de rotinas

O learner já coleta interações; este módulo fecha o ciclo: observa padrões
recorrentes (mesma ação, no mesmo horário, em dias diferentes) e sugere
proativamente criar uma rotina/automação.

Como agrupa
-----------
Cada interação bem-sucedida vira uma "assinatura" curta (verbo + alvo, sem
artigos nem valores variáveis). Se a mesma assinatura aparece em >= N dias
distintos por volta do mesmo horário (janela de ±1h), é um hábito candidato.

Roda também sozinho (scheduler diário), avisando só quando descobre um hábito
novo — o que já foi sugerido fica registrado para não repetir.
"""

import json
import logging
import re
import threading
import time
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

_running = False
_thread: "threading.Thread | None" = None
_CHECK_INTERVAL = 1800  # 30 min entre verificações do scheduler
_last_run_ts = 0.0

_STOPWORDS = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
    "no", "na", "nos", "nas", "pra", "para", "por", "meu", "minha",
    "favor", "me", "e",
}


def _config():
    from core.config import Config
    return Config()


def _signature(text: str) -> str:
    """Reduz um comando a uma assinatura curta e estável para agrupar hábitos."""
    t = text.lower().strip()
    t = re.sub(r"[^\wçãáàâéêíóôõú\s]", " ", t)
    t = re.sub(r"\d+", "", t)
    tokens = [w for w in t.split() if w and w not in _STOPWORDS]
    return " ".join(tokens[:4]).strip()


def _load_interactions(limit: int = 1000) -> list[dict]:
    try:
        from storage.memory import get_recent
        return get_recent(limit)
    except Exception:
        return []


def detect_habits(min_days: int | None = None) -> list[dict]:
    """Retorna hábitos candidatos: [{signature, hour, days, sample}]."""
    if min_days is None:
        try:
            min_days = int(_config().get("habits.min_days", 3))
        except Exception:
            min_days = 3

    interactions = _load_interactions()
    if not interactions:
        return []

    # signature -> { (date, hour) } e exemplo de comando
    buckets: dict[str, set] = defaultdict(set)
    samples: dict[str, str] = {}
    hour_counts: dict[str, list] = defaultdict(list)

    for it in interactions:
        if not it.get("success", 1):
            continue
        raw = (it.get("raw_input") or "").strip()
        sig = _signature(raw)
        if not sig or len(sig) < 3:
            continue
        ts = it.get("ts") or ""
        try:
            dt = datetime.fromisoformat(ts)
        except Exception:
            continue
        buckets[sig].add((dt.date().isoformat(), dt.hour))
        hour_counts[sig].append(dt.hour)
        samples.setdefault(sig, raw)

    habits = []
    for sig, entries in buckets.items():
        hours = hour_counts[sig]
        if not hours:
            continue
        # horário típico = hora mais frequente
        typical = max(set(hours), key=hours.count)
        # dias distintos dentro da janela de ±1h do horário típico
        days = {d for (d, h) in entries if abs(h - typical) <= 1}
        if len(days) >= min_days:
            habits.append({
                "signature": sig,
                "hour": typical,
                "days": len(days),
                "sample": samples.get(sig, sig),
            })

    habits.sort(key=lambda h: h["days"], reverse=True)
    return habits


def _format(habit: dict) -> str:
    return (f"Você costuma \"{habit['sample']}\" por volta das {habit['hour']:02d}h "
            f"({habit['days']} dias). Quer que eu crie uma rotina automática pra isso?")


# ── Comando de voz/texto ───────────────────────────────────────────────

def suggest(*_) -> str:
    """Lista hábitos detectados e sugere automações."""
    try:
        enabled = bool(_config().get("habits.enabled", True))
    except Exception:
        enabled = True
    if not enabled:
        return "Detecção de hábitos desativada (habits.enabled: false)."

    habits = detect_habits()
    if not habits:
        return ("Ainda não detectei nenhum padrão forte o suficiente. "
                "Continue usando que eu vou aprendendo sua rotina.")

    lines = ["Notei alguns padrões no seu uso:"]
    for h in habits[:5]:
        lines.append(f"  • {_format(h)}")
    return "\n".join(lines)


# ── Sugestão proativa (sem comando do usuário) ─────────────────────────

def _shown_signatures() -> set:
    try:
        from storage.memory import get_preference
        return set(json.loads(get_preference("habits_shown", "[]")))
    except Exception:
        return set()


def _mark_shown(signatures: set) -> None:
    try:
        from storage.memory import set_preference
        set_preference("habits_shown", json.dumps(sorted(signatures), ensure_ascii=False))
    except Exception:
        pass


def _fire_new_habits() -> None:
    habits = detect_habits()
    if not habits:
        return
    shown = _shown_signatures()
    new = [h for h in habits if h["signature"] not in shown]
    if not new:
        return

    top = new[0]
    msg = _format(top)
    try:
        from output.notifier import notify
        notify("Paçoca — Padrão detectado", "Encontrei um hábito que pode virar rotina. Diga 'sugestões'.")
    except Exception:
        pass
    try:
        from web.app import push_event
        push_event("info", f"🔁 {msg}")
    except Exception:
        pass
    logger.info("Hábito novo detectado: %s", top["signature"])
    print(f"\n[Paçoca] 🔁 {msg}\n")

    _mark_shown(shown | {h["signature"] for h in new})


def _scheduler_loop() -> None:
    global _last_run_ts
    while _running:
        try:
            cfg = _config()
            if cfg.get("habits.enabled", True):
                interval_s = float(cfg.get("habits.interval_hours", 24)) * 3600
                if interval_s > 0 and time.monotonic() - _last_run_ts >= interval_s:
                    _last_run_ts = time.monotonic()
                    _fire_new_habits()
        except Exception as e:
            logger.error("Erro no scheduler de hábitos: %s", e)
        time.sleep(_CHECK_INTERVAL)


def start_scheduler() -> None:
    """Inicia a verificação periódica de hábitos (idempotente)."""
    global _running, _thread, _last_run_ts
    if _running:
        return
    _running = True
    _last_run_ts = time.monotonic()  # primeira análise só após o intervalo completo
    _thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _thread.start()


def stop_scheduler() -> None:
    global _running
    _running = False
