"""
modules/summarizer.py — Integração com IA local (Ollama) e cloud (Groq)
Geração de resumos, explicações e respostas livres.
"""

import logging
import requests
import json
import os

logger = logging.getLogger(__name__)

# Instância lazy da config (injetada pelo orchestrator via módulo)
_config = None


def _get_config():
    global _config
    if _config is None:
        from core.config import Config
        _config = Config()
    return _config


def ask_ai(prompt: str, system: str = None, use_context: bool = True) -> str:
    """
    Envia um prompt ao LLM configurado e retorna a resposta.
    Usa Ollama por padrão; fallback para Anthropic se configurado.
    use_context=True injeta o histórico da sessão no prompt.
    """
    config = _get_config()
    provider = config.get("ai.provider", "ollama")

    if system is None:
        from core.profiles import _get_manager
        system = _get_manager().system_prompt()

    if use_context and config.get("ai.use_context", True):
        from storage.context import build_context_prompt
        prompt = build_context_prompt(prompt)

    if provider == "ollama":
        return _ask_ollama(prompt, system, config)
    elif provider == "groq":
        return _ask_groq(prompt, system, config)
    return "Provedor de IA não configurado."


def _ask_ollama(prompt: str, system: str, config) -> str:
    url = config.get("ai.ollama_url", "http://localhost:11434") + "/api/generate"
    model = config.get("ai.model", "llama3")
    max_tokens = config.get("ai.max_tokens", 1024)

    try:
        resp = requests.post(
            url,
            json={
                "model": model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {"num_predict": max_tokens},
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.ConnectionError:
        return (
            "Ollama não está rodando. "
            "Inicie com: ollama serve"
        )
    except requests.Timeout:
        return "Timeout: o modelo demorou muito para responder."
    except Exception as e:
        logger.error(f"Erro Ollama: {e}")
        return f"Erro ao consultar IA: {e}"


def _ask_groq(prompt: str, system: str, config) -> str:
    api_key = config.get("ai.groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "GROQ_API_KEY não definida. Obtenha gratuitamente em console.groq.com"
    model = os.environ.get("GROQ_MODEL") or config.get("ai.groq_model", "llama-3.1-8b-instant")
    max_tokens = config.get("ai.max_tokens", 1024)
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.Timeout:
        return "Não entendi o comando. Pode repetir?"
    except Exception as e:
        logger.error(f"Erro Groq: {e}")
        return "Não consegui processar isso. Pode tentar de novo?"


# ── Funções de alto nível ──────────────────────────────────────────────

def summarize_last(*_) -> str:
    """Resume a última transcrição salva."""
    from storage.file_store import load_last_transcription
    text = load_last_transcription()
    if not text:
        return "Nenhuma transcrição disponível para resumir."
    return summarize(text, detailed=False)


def summarize_detailed(*_) -> str:
    """Resume a última transcrição com mais detalhes."""
    from storage.file_store import load_last_transcription
    text = load_last_transcription()
    if not text:
        return "Nenhuma transcrição disponível."
    return summarize(text, detailed=True)


def summarize(text: str, detailed: bool = False) -> str:
    if detailed:
        prompt = (
            f"Faça um resumo DETALHADO do seguinte texto, "
            f"organizando em tópicos com subtópicos:\n\n{text}"
        )
    else:
        prompt = (
            f"Faça um resumo CURTO (máximo 5 bullet points) "
            f"do seguinte texto:\n\n{text}"
        )
    return ask_ai(prompt)


def explain(topic: str, *_) -> str:
    """Explica um conceito de forma clara e objetiva."""
    return ask_ai(f"Explique de forma clara e objetiva: {topic}")


def summarize_meeting(*_) -> str:
    """Gera um sumário estruturado da última reunião transcrita."""
    from storage.file_store import load_last_transcription
    text = load_last_transcription()
    if not text:
        return "Nenhuma transcrição disponível. Grave uma reunião com 'começa a transcrever'."

    prompt = (
        "Analise a transcrição de reunião abaixo e gere um sumário estruturado em português. "
        "Organize obrigatoriamente nas seguintes seções:\n\n"
        "## Resumo executivo\n(2-3 frases)\n\n"
        "## Tópicos discutidos\n(lista de bullet points)\n\n"
        "## Decisões tomadas\n(o que foi decidido objetivamente)\n\n"
        "## Action items\n(próximos passos com responsável, se mencionado)\n\n"
        "## Pendências\n(pontos sem resolução ou que precisam de follow-up)\n\n"
        f"Transcrição:\n{text}"
    )
    return ask_ai(prompt, use_context=False)


def summarize_session(*_) -> str:
    """Resumo do que foi feito na sessão atual (baseado no contexto)."""
    from storage.context import get_turns
    turns = get_turns()
    if not turns:
        return "Nenhuma interação no contexto atual."
    history = "\n".join(f"- {cmd}" for cmd, _ in turns)
    prompt = (
        f"Liste de forma concisa o que o usuário fez nesta sessão:\n{history}\n\n"
        "Gere um resumo em 3-5 bullet points do que foi realizado."
    )
    return ask_ai(prompt, use_context=False)
