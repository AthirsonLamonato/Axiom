"""
modules/learner.py — Motor de aprendizado e auto-otimização
Analisa interações passadas, aprende vocabulário, detecta padrões
e melhora o sistema de roteamento ao longo do tempo.
"""

import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)


# ── Registro de interação (chamado após cada comando) ──────────────────

def record(raw_input: str, response: str, action: str = "",
           resolved: str = "", success: bool = True, source: str = "voice"):
    """Registra a interação e aciona aprendizado incremental."""
    from storage.memory import log_interaction, record_usage
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
    if corrected.lower() != text.lower():
        logger.info("Transcrição corrigida: '%s' → '%s'", text, corrected)
    return corrected
