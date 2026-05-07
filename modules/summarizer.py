"""
modules/summarizer.py — Integração com IA local (Ollama) e cloud (Anthropic)
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


def ask_ai(prompt: str, system: str = None) -> str:
    """
    Envia um prompt ao LLM configurado e retorna a resposta.
    Usa Ollama por padrão; fallback para Anthropic se configurado.
    """
    config = _get_config()
    provider = config.get("ai.provider", "ollama")

    if system is None:
        from core.profiles import ProfileManager
        system = ProfileManager(config).system_prompt()

    if provider == "ollama":
        return _ask_ollama(prompt, system, config)
    elif provider == "anthropic":
        return _ask_anthropic(prompt, system, config)
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


def _ask_anthropic(prompt: str, system: str, config) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "ANTHROPIC_API_KEY não definida."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=config.get("ai.max_tokens", 1024),
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except ImportError:
        return "Biblioteca anthropic não instalada: pip install anthropic"
    except Exception as e:
        logger.error(f"Erro Anthropic: {e}")
        return f"Erro ao consultar Anthropic: {e}"


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
