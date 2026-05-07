"""
modules/search.py — Pesquisa inteligente com roteamento automático
Decide entre IA local (Ollama) e busca na web (DuckDuckGo) conforme o contexto.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Padrões que indicam necessidade de informação factual/atual → web
WEB_PATTERNS = [
    r"clima",
    r"previsão",
    r"notícia",
    r"hoje",
    r"agora",
    r"preço",
    r"cotação",
    r"quando (foi|aconteceu|é)",
    r"quem (é|foi|ganhou)",
    r"resultado",
    r"placar",
]


def route(query: str, *_) -> str:
    """
    Roteia automaticamente: se a query parece factual/atual → web,
    caso contrário → IA local.
    """
    if _is_web_query(query):
        logger.debug(f"Roteando para web: {query}")
        return search_web(query)
    logger.debug(f"Roteando para IA: {query}")
    return search_ai(query)


def search_ai(query: str, *_) -> str:
    """Responde usando o LLM local."""
    from modules.summarizer import ask_ai
    return ask_ai(query)


def search_web(query: str, *_) -> str:
    """Busca no DuckDuckGo e resume os resultados com IA."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "duckduckgo-search não instalado: pip install duckduckgo-search"

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=4))

        if not results:
            return f"Nenhum resultado encontrado para '{query}'."

        snippets = "\n\n".join(
            f"Fonte: {r.get('href', '')}\n{r.get('body', '')}"
            for r in results
        )

        from modules.summarizer import ask_ai
        summary = ask_ai(
            f"Com base nestas informações da internet, responda: '{query}'\n\n{snippets}",
            system="Seja objetivo. Cite a fonte quando relevante. Responda em português.",
        )
        return summary

    except Exception as e:
        logger.error(f"Erro na busca web: {e}")
        return f"Erro na busca: {e}"


def _is_web_query(query: str) -> bool:
    q = query.lower()
    return any(re.search(p, q) for p in WEB_PATTERNS)
