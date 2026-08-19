"""
modules/learner.py — Motor de aprendizado e auto-otimização
Analisa interações passadas, aprende vocabulário, detecta padrões
e melhora o sistema de roteamento ao longo do tempo.
"""

import logging
import re
import threading
import time

logger = logging.getLogger(__name__)

_scheduler_running = False
_scheduler_thread: "threading.Thread | None" = None
_last_run_ts: float = 0.0
_CHECK_INTERVAL = 300  # segundos entre verificações do agendador


# ── Registro de interação (chamado após cada comando) ──────────────────

def record(raw_input: str, response: str, action: str = "",
           resolved: str = "", success: bool = True, source: str = "voice"):
    """Registra a interação e aciona aprendizado incremental."""
    from storage.memory import log_interaction
    log_interaction(raw_input, response, action, resolved, success, source)

    # Extrai recursos usados para estatísticas
    _extract_and_record_usage(action, raw_input, response)


def _extract_and_record_usage(action: str, command: str, response: str):
    from storage.memory import record_usage

    if "open_application" in action or "open_app" in action:
        app = _extract_word_after(command, ["abre", "abrir", "open"])
        if app:
            record_usage(app, "app")

    elif "open_browser" in action or "open_browser_with_search" in action:
        browser = _extract_word_after(command, ["abre", "abrir"])
        if browser:
            record_usage(browser, "app")
        site = _extract_word_after(command, ["no", "na", "em", "pesquisa", "busca"])
        if site:
            record_usage(site, "browser")

    elif "spotify" in action or "control_media" in action:
        query = _extract_word_after(command, ["toca", "tocar", "play", "playlist"])
        if query:
            record_usage(query, "music")


def _extract_word_after(text: str, keywords: list[str]) -> str:
    text_lower = text.lower()
    for kw in keywords:
        idx = text_lower.find(kw)
        if idx != -1:
            rest = text[idx + len(kw):].strip()
            # Remove artigos iniciais
            rest = re.sub(r'^(o|a|os|as|um|uma)\s+', '', rest, flags=re.IGNORECASE)
            # Pega até a próxima preposição ou fim
            word = re.split(r'\s+(e|no|na|em|para|pra)\s+', rest)[0].strip()
            if word and len(word) > 2:
                return word[:50]
    return ""


# ── Aprendizado de vocabulário ─────────────────────────────────────────

def learn_vocabulary_from_correction(heard: str, intended: str):
    """
    Registra que quando o Whisper transcreve `heard`, o usuário quis dizer `intended`.
    Ex: learn_vocabulary_from_correction("ikálika", "icônica")
    """
    from storage.memory import add_vocabulary
    add_vocabulary(heard, intended)
    logger.info("Vocabulário aprendido: '%s' → '%s'", heard, intended)


def rollback_last(*_) -> str:
    from storage.memory import rollback_last_learning
    return rollback_last_learning()


def detect_misrecognition(raw: str, command_worked: bool) -> None:
    """
    Se um comando não funcionou, analisa se o problema pode ser de transcrição
    e salva para revisão posterior.
    """
    if not command_worked and len(raw.split()) <= 5:
        from storage.memory import add_learned_pattern
        add_learned_pattern(raw, "UNKNOWN", "")
        logger.debug("Padrão desconhecido registrado: '%s'", raw)


# ── Análise periódica ──────────────────────────────────────────────────

def analyze_and_optimize() -> str:
    """
    Analisa o histórico de interações e retorna um relatório de aprendizado.
    Pode ser chamado manualmente ou via rotina agendada.
    """
    from storage.memory import get_recent, get_top_used, get_vocabulary

    report = []
    interactions = get_recent(100)

    if not interactions:
        return "Nenhuma interação registrada ainda."

    # Taxa de sucesso
    total = len(interactions)
    failed = sum(1 for i in interactions if not i.get("success", 1))
    rate = ((total - failed) / total) * 100
    report.append(f"Taxa de sucesso: {rate:.0f}% ({total - failed}/{total} comandos)")

    # Apps mais usados
    top_apps = get_top_used("app", 5)
    if top_apps:
        report.append("Apps mais usados: " + ", ".join(f"{r['resource']} ({r['count']}x)" for r in top_apps))

    # Músicas mais tocadas
    top_music = get_top_used("music", 3)
    if top_music:
        report.append("Músicas/playlists favoritas: " + ", ".join(f"{r['resource']} ({r['count']}x)" for r in top_music))

    # Vocabulário aprendido
    vocab = get_vocabulary()
    if vocab:
        report.append(f"Vocabulário aprendido: {len(vocab)} correção(ões)")

    return "\n".join(report)


def get_personalized_context() -> str:
    """
    Monta contexto personalizado para injetar nos prompts do LLM.
    Inclui preferências, apps favoritos e padrões de uso.
    """
    from storage.memory import build_memory_context
    return build_memory_context()


# ── Correção automática de transcrição ────────────────────────────────

def correct_transcription(text: str) -> str:
    """
    Aplica vocabulário aprendido para corrigir erros recorrentes do Whisper.
    """
    from storage.memory import apply_vocabulary
    corrected = apply_vocabulary(text)
    # Correções conservadoras para erros recorrentes do Whisper em nomes que
    # fazem parte do vocabulário do assistente. Regras aprendidas pelo usuário
    # continuam tendo prioridade porque foram aplicadas acima.
    replacements = (
        (r"\b(?:spot\s*fire|esporte\s*fi|spotify)\b", "Spotify"),
        (r"\b(?:javis|jarves)\b", "Jarvis"),
        (r"\b(?:cromi|crômio)\b", "Chrome"),
    )
    for pattern, replacement in replacements:
        corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)

    # Remove pedidos de cortesia que não alteram a intenção e frequentemente
    # impediam uma rota direta de casar com o início da frase.
    corrected = re.sub(
        r"^\s*(?:(?:ei|ol[aá])\s+pa[çc]oca[, ]+)?"
        r"(?:(?:voc[eê]\s+)?pode(?:ria)?|por\s+favor|eu\s+quero\s+que\s+voc[eê])\s+",
        "",
        corrected,
        flags=re.IGNORECASE,
    )
    corrected = re.sub(r"\s+(?:pra|para)\s+mim\b", "", corrected, flags=re.IGNORECASE)
    corrected = re.sub(r"\s+por\s+favor\s*[.!?]*$", "", corrected, flags=re.IGNORECASE)
    corrected = corrected.strip()
    if corrected.lower() != text.lower():
        logger.info("Transcrição corrigida: '%s' → '%s'", text, corrected)
    return corrected


# ── Aprendizado proativo (sem comando do usuário) ───────────────────────

def _fire_insight() -> None:
    report = analyze_and_optimize()
    if not report or report.startswith("Nenhuma interação"):
        return

    try:
        from storage.file_store import save_text
        path = save_text(report, prefix="learning_insight", ext="md")
        logger.info("Insight de aprendizado salvo em %s", path)
    except Exception as e:
        logger.debug("Não foi possível salvar insight de aprendizado: %s", e)

    try:
        from output.notifier import notify
        notify("Paçoca — Aprendizado", "Novo insight de uso disponível. Diga 'o que você aprendeu'.")
    except Exception as e:
        logger.debug("Notificação de aprendizado indisponível: %s", e)
    try:
        from web.app import push_event
        push_event("info", "🧠 Novo insight de aprendizado gerado")
    except Exception as e:
        logger.debug("Dashboard de aprendizado indisponível: %s", e)


def _scheduler_loop() -> None:
    global _last_run_ts
    while _scheduler_running:
        try:
            from core.config import Config
            config = Config()
            if config.get("learner.proactive_enabled", True):
                interval_s = float(config.get("learner.interval_hours", 24)) * 3600
                if interval_s > 0 and time.monotonic() - _last_run_ts >= interval_s:
                    _last_run_ts = time.monotonic()
                    _fire_insight()
        except Exception as e:
            logger.error("Erro no agendador de aprendizado: %s", e)
        time.sleep(_CHECK_INTERVAL)


def start_scheduler() -> None:
    """Inicia a verificação periódica de insights de aprendizado (idempotente)."""
    global _scheduler_running, _scheduler_thread, _last_run_ts
    if _scheduler_running:
        return
    _scheduler_running = True
    _last_run_ts = time.monotonic()  # primeira análise só após o intervalo completo
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()


def stop_scheduler() -> None:
    global _scheduler_running
    _scheduler_running = False
