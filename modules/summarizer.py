"""
modules/summarizer.py — Integração com IA via cliente central (core/providers.py)
Local-first por padrão: Ollama, com Groq opcional e fallback automático.
"""

import logging

logger = logging.getLogger(__name__)

_config = None


def _get_config():
    global _config
    if _config is None:
        from core.config import Config
        _config = Config()
    return _config


def _client():
    from core.providers import get_client
    return get_client(_get_config())


def ask_ai(prompt: str, system: str = None, use_context: bool = True) -> str:
    """
    Envia um prompt ao LLM e retorna a resposta.
    Usa o provedor configurado em core/providers.py.
    """
    config = _get_config()

    if system is None:
        try:
            from core.profiles import _get_manager
            system = _get_manager().system_prompt()
        except Exception:
            system = "Você é Paçoca, um assistente pessoal útil. Responda em português."

    if use_context and config.get("ai.use_context", True):
        try:
            from storage.context import build_context_prompt
            prompt = build_context_prompt(prompt)
        except Exception:
            pass

    messages = [{"role": "user", "content": prompt}]
    result = _client().chat(messages, system=system, max_tokens=config.get("ai.max_tokens", 1024))
    return result or (
        "Não consegui acessar o modelo de IA. Execute 'python main.py --doctor' "
        "para verificar Ollama, modelo local e dependências."
    )


def ask_ai_stream(prompt: str, system: str = None):
    """Versão streaming de ask_ai. Retorna Generator[str]."""
    config = _get_config()
    if system is None:
        try:
            from core.profiles import _get_manager
            system = _get_manager().system_prompt()
        except Exception:
            system = "Você é Paçoca, um assistente pessoal útil. Responda em português."
    messages = [{"role": "user", "content": prompt}]
    return _client().chat(messages, system=system,
                          max_tokens=config.get("ai.max_tokens", 1024), stream=True)


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
    return ask_ai(f"Explique de forma clara e objetiva: {topic}")


def summarize_meeting(*_) -> str:
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
