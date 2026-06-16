"""
core/embeddings.py — Provedor de embeddings para memória semântica

Mesmo padrão arquitetural de core/providers.py (LLMClient): backend
configurável, circuit breaker próprio, cache TTL, nunca propaga exceção.

Backends gratuitos suportados (ai.embeddings_provider):
  - gemini : API REST gratuita do Google AI Studio (requer GEMINI_API_KEY)
  - ollama : local, via /api/embeddings (requer `ollama pull nomic-embed-text`)
  - auto   : tenta gemini se houver chave, senão ollama, senão None (padrão)
  - none   : desabilita — chamador cai no fallback de busca por palavra-chave

embed_text() nunca levanta exceção: retorna None em qualquer falha, para que
o código chamador (storage/knowledge_base.py) sempre tenha um caminho de
fallback seguro sem precisar de try/except próprio.
"""

import array
import logging
import threading
import time
from typing import Optional

from core.providers import _TTLCache, _get_session, _resolve_key, _retry_http, cached_get

logger = logging.getLogger(__name__)

# ── Circuit breaker próprio (estado separado do circuit breaker do Groq) ──
_EMBED_CB_THRESHOLD = 3
_EMBED_CB_RESET_SECS = 120
_embed_failures: int = 0
_embed_open_until: float = 0.0
_embed_circuit_lock = threading.Lock()

_embed_cache = _TTLCache(ttl=3600)  # embeddings são deterministicos por texto+modelo


def _embed_circuit_is_open() -> bool:
    with _embed_circuit_lock:
        return time.monotonic() < _embed_open_until


def _record_embed_failure() -> None:
    global _embed_failures, _embed_open_until
    with _embed_circuit_lock:
        _embed_failures += 1
        if _embed_failures >= _EMBED_CB_THRESHOLD:
            _embed_open_until = time.monotonic() + _EMBED_CB_RESET_SECS
            logger.warning(
                "Circuit breaker de embeddings ABERTO: %d falhas consecutivas. "
                "Pausando por %ds (busca semântica cai para palavra-chave nesse intervalo).",
                _embed_failures, _EMBED_CB_RESET_SECS,
            )


def _record_embed_success() -> None:
    global _embed_failures, _embed_open_until
    with _embed_circuit_lock:
        _embed_failures = 0
        _embed_open_until = 0.0


# ── Empacotamento compacto (BLOB SQLite, sem dependência de numpy) ─────

def pack_embedding(vec: list[float]) -> bytes:
    return array.array("f", vec).tobytes()


def unpack_embedding(blob: bytes) -> list[float]:
    arr = array.array("f")
    arr.frombytes(blob)
    return list(arr)


# ── Similaridade ────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Backends ────────────────────────────────────────────────────────────

def _gemini_embed(text: str, config) -> Optional[list[float]]:
    key = _resolve_key("ai.embeddings_api_key", "GEMINI_API_KEY", config)
    if not key:
        return None
    model = config.get("ai.embeddings_model", "text-embedding-004")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={key}"
    body = {"model": f"models/{model}", "content": {"parts": [{"text": text}]}}
    try:
        session = _get_session()
        resp = _retry_http(
            lambda: session.post(url, json=body, timeout=10),
            max_attempts=2,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]
    except Exception as e:
        logger.debug("Gemini embeddings falhou: %s", e)
        return None


def _ollama_embed(text: str, config) -> Optional[list[float]]:
    ollama_url = config.get("ai.ollama_url", "http://localhost:11434")
    model = config.get("ai.embeddings_ollama_model", "nomic-embed-text")
    try:
        session = _get_session()
        resp = _retry_http(
            lambda: session.post(
                f"{ollama_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=15,
            ),
            max_attempts=2,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]
    except Exception as e:
        logger.debug("Ollama embeddings falhou: %s", e)
        return None


def _dispatch(text: str, config) -> Optional[list[float]]:
    provider = config.get("ai.embeddings_provider", "auto")
    if provider == "none":
        return None
    if provider == "gemini":
        return _gemini_embed(text, config)
    if provider == "ollama":
        return _ollama_embed(text, config)
    # auto: Gemini se houver chave configurada, senão Ollama
    if _resolve_key("ai.embeddings_api_key", "GEMINI_API_KEY", config):
        vec = _gemini_embed(text, config)
        if vec is not None:
            return vec
    return _ollama_embed(text, config)


def embed_text(text: str, config=None) -> Optional[list[float]]:
    """
    Calcula o embedding de um texto. Retorna None se nenhum backend estiver
    configurado/disponível ou se a chamada falhar — nunca levanta exceção.
    """
    if not text or not text.strip():
        return None
    if config is None:
        from core.config import Config
        config = Config()

    if _embed_circuit_is_open():
        return None

    provider = config.get("ai.embeddings_provider", "auto")
    if provider == "none":
        return None
    model = config.get("ai.embeddings_model", "text-embedding-004")
    cache_key = f"{provider}:{model}:{hash(text)}"

    def _fetch():
        vec = _dispatch(text, config)
        if vec is not None:
            _record_embed_success()
        else:
            _record_embed_failure()
        return vec

    return cached_get(_embed_cache, cache_key, _fetch)
