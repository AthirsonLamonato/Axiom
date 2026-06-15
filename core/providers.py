"""
core/providers.py — Cliente HTTP centralizado para todos os provedores de IA

Funcionalidades:
  - Interface única: LLMClient.chat() → Groq (online) ou Ollama (local)
  - Retry com backoff exponencial para 429, 502, 503, timeouts
  - Circuit breaker: após N falhas Groq consecutivas, usa Ollama temporariamente
  - Logs sanitizados: API keys nunca aparecem em log
  - Métricas opcionais: latência, tokens, provedor usado
"""

import logging
import random
import time
from typing import Any, Generator, Optional

import requests

logger = logging.getLogger(__name__)

# ── Configurações do circuit breaker ─────────────────────────────────
_CB_THRESHOLD = 3        # falhas consecutivas antes de abrir o circuito
_CB_RESET_SECS = 120     # segundos antes de testar Groq novamente

# Estado do circuit breaker (módulo-level — compartilhado no processo)
_groq_failures: int = 0
_groq_open_until: float = 0.0

# ── Timeouts padrão por serviço (segundos) ───────────────────────────
TIMEOUTS = {
    "groq":    20,
    "ollama":  45,
    "search":  10,
    "weather": 8,
    "finance": 8,
    "spotify": 10,
}

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_STREAM_URL = "https://api.groq.com/openai/v1/chat/completions"


# ── Helpers ───────────────────────────────────────────────────────────

def _redact_auth(headers: dict) -> dict:
    """Remove Authorization header value dos logs."""
    safe = dict(headers)
    if "Authorization" in safe:
        safe["Authorization"] = "Bearer ***"
    return safe


def _circuit_is_open() -> bool:
    return time.monotonic() < _groq_open_until


def _record_groq_failure() -> None:
    global _groq_failures, _groq_open_until
    _groq_failures += 1
    if _groq_failures >= _CB_THRESHOLD:
        _groq_open_until = time.monotonic() + _CB_RESET_SECS
        logger.warning(
            "Circuit breaker ABERTO: Groq falhou %d vezes consecutivas. "
            "Usando Ollama por %ds.",
            _groq_failures, _CB_RESET_SECS,
        )


def _record_groq_success() -> None:
    global _groq_failures, _groq_open_until
    if _groq_failures > 0:
        logger.info("Circuit breaker FECHADO: Groq respondeu com sucesso.")
    _groq_failures = 0
    _groq_open_until = 0.0


def _retry_http(fn, *, max_attempts: int = 3, base_delay: float = 1.0) -> requests.Response:
    """
    Executa fn() com retry exponencial para erros recuperáveis.
    Recuperável: 429 (rate limit), 502/503 (server error), ConnectionError, Timeout.
    """
    for attempt in range(max_attempts):
        try:
            resp = fn()
            if resp.status_code in (429, 502, 503) and attempt < max_attempts - 1:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), 16.0)
                logger.warning("HTTP %s — retry em %.1fs (tentativa %d/%d)",
                               resp.status_code, delay, attempt + 1, max_attempts)
                time.sleep(delay)
                continue
            return resp
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt == max_attempts - 1:
                raise
            delay = min(base_delay * (2 ** attempt), 8.0)
            logger.warning("Erro de rede: %s — retry em %.1fs", e, delay)
            time.sleep(delay)
    raise RuntimeError("Nunca deveria chegar aqui")


def _resolve_key(config_key: str, env_var: str, config) -> str:
    """
    Resolve chave de API na seguinte ordem de prioridade:
      1. Variável de ambiente (mais segura)
      2. keyring do sistema (se disponível)
      3. config.yaml (funciona, mas exibe aviso)
    Nunca loga o valor da chave.
    """
    import os
    key = os.environ.get(env_var, "")
    if key:
        return key

    try:
        import keyring
        stored = keyring.get_password("pacoca", env_var.lower())
        if stored:
            return stored
    except Exception:
        pass

    yaml_key = config.get(config_key, "") if config else ""
    if yaml_key:
        logger.warning(
            "Chave '%s' encontrada no config.yaml — considere mover para .env ou keyring.",
            config_key,
        )
    return yaml_key


# ── LLM Client ────────────────────────────────────────────────────────

class LLMClient:
    """
    Cliente de LLM online-first: Groq como principal, Ollama como fallback.

    Uso:
        client = LLMClient(config)
        text   = client.chat(messages)
        text   = client.chat(messages, tools=TOOLS, tool_choice="auto")

    Streaming (retorna Generator[str, None, None]):
        for chunk in client.chat(messages, stream=True):
            print(chunk, end="", flush=True)
    """

    def __init__(self, config):
        self.config = config
        self._groq_key: Optional[str] = None

    def _get_groq_key(self) -> str:
        if not self._groq_key:
            self._groq_key = _resolve_key("ai.groq_api_key", "GROQ_API_KEY", self.config)
        return self._groq_key

    def _groq_model(self) -> str:
        import os
        return os.environ.get("GROQ_MODEL") or self.config.get(
            "ai.groq_model", "llama-3.3-70b-versatile"
        )

    def _ollama_model(self) -> str:
        return self.config.get("ai.model", "llama3")

    def _ollama_url(self) -> str:
        return self.config.get("ai.ollama_url", "http://localhost:11434")

    # ── Interface pública ────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> Any:
        """
        Envia mensagens ao LLM. Retorna str (ou Generator se stream=True).
        Tenta Groq primeiro; cai para Ollama se circuit breaker aberto ou se Groq falhar.
        """
        if system:
            messages = [{"role": "system", "content": system}] + list(messages)

        # Trunca contexto muito longo antes de enviar
        messages = _truncate_messages(messages, max_chars=24_000)

        provider = self.config.get("ai.provider", "groq")
        groq_key = self._get_groq_key()

        # Tenta Groq se configurado E circuit breaker fechado
        if provider in ("groq", "auto") and groq_key and not _circuit_is_open():
            try:
                if stream:
                    return self._groq_stream(messages, tools, tool_choice, max_tokens)
                return self._groq_chat(messages, tools, tool_choice, max_tokens)
            except Exception as e:
                _record_groq_failure()
                logger.warning("Groq falhou (%s) — usando Ollama como fallback.", e)

        # Fallback para Ollama (sem suporte a tools)
        if stream:
            return self._ollama_stream(messages, max_tokens)
        return self._ollama_chat(messages, max_tokens)

    def chat_raw(self, messages: list[dict], **kwargs) -> dict:
        """Retorna o dict completo da resposta Groq (útil para tool_calls)."""
        messages = _truncate_messages(messages, max_chars=24_000)
        groq_key = self._get_groq_key()
        if not groq_key or _circuit_is_open():
            raise RuntimeError("Groq indisponível — circuit breaker aberto ou sem chave.")
        return self._groq_raw(messages, **kwargs)

    # ── Groq ────────────────────────────────────────────────────────

    def _groq_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_groq_key()}",
            "Content-Type": "application/json",
        }

    def _groq_body(self, messages, tools=None, tool_choice=None, max_tokens=1024, stream=False) -> dict:
        body: dict = {
            "model": self._groq_model(),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice
        return body

    def _groq_raw(self, messages, tools=None, tool_choice=None, max_tokens=1024) -> dict:
        t0 = time.monotonic()
        headers = self._groq_headers()
        body = self._groq_body(messages, tools, tool_choice, max_tokens)
        logger.debug("Groq request: model=%s tools=%s", body["model"], bool(tools))

        resp = _retry_http(
            lambda: requests.post(_GROQ_URL, headers=headers, json=body,
                                  timeout=TIMEOUTS["groq"]),
        )
        if resp.status_code == 401:
            self._groq_key = None  # invalida cache da chave
            raise RuntimeError("Groq 401 — verifique a GROQ_API_KEY.")
        resp.raise_for_status()
        data = resp.json()

        _record_groq_success()
        latency = time.monotonic() - t0
        usage = data.get("usage", {})
        logger.debug("Groq OK: %.2fs | tokens in=%s out=%s",
                     latency, usage.get("prompt_tokens", "?"), usage.get("completion_tokens", "?"))

        # Registra métricas de observabilidade
        _emit_metric("groq", latency, usage)
        return data

    def _groq_chat(self, messages, tools=None, tool_choice=None, max_tokens=1024) -> str:
        data = self._groq_raw(messages, tools, tool_choice, max_tokens)
        return (data["choices"][0]["message"].get("content") or "").strip()

    def _groq_stream(self, messages, tools=None, tool_choice=None,
                     max_tokens=1024) -> Generator[str, None, None]:
        headers = self._groq_headers()
        body = self._groq_body(messages, tools, tool_choice, max_tokens, stream=True)
        try:
            with requests.post(_GROQ_STREAM_URL, headers=headers, json=body,
                               stream=True, timeout=TIMEOUTS["groq"]) as resp:
                if resp.status_code == 401:
                    self._groq_key = None
                    raise RuntimeError("Groq 401 — verifique a GROQ_API_KEY.")
                resp.raise_for_status()
                _record_groq_success()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    raw = line.decode("utf-8", errors="ignore")
                    if raw.startswith("data: "):
                        raw = raw[6:]
                    if raw == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(raw)
                        delta = chunk["choices"][0].get("delta", {})
                        text = delta.get("content") or ""
                        if text:
                            yield text
                    except Exception:
                        pass
        except Exception as e:
            _record_groq_failure()
            logger.warning("Groq stream falhou: %s — sem fallback de streaming", e)

    # ── Ollama ──────────────────────────────────────────────────────

    def _ollama_chat(self, messages: list[dict], max_tokens: int = 1024) -> str:
        url = self._ollama_url() + "/api/chat"
        try:
            resp = _retry_http(
                lambda: requests.post(
                    url,
                    json={
                        "model": self._ollama_model(),
                        "messages": messages,
                        "stream": False,
                        "options": {"num_predict": max_tokens, "temperature": 0.3},
                    },
                    timeout=TIMEOUTS["ollama"],
                ),
                max_attempts=2,
            )
            resp.raise_for_status()
            t0 = time.monotonic()
            content = resp.json().get("message", {}).get("content", "").strip()
            _emit_metric("ollama", time.monotonic() - t0, {})
            return content
        except Exception as e:
            logger.warning("Ollama indisponível: %s", e)
            return ""

    def _ollama_stream(self, messages: list[dict], max_tokens: int = 1024) -> Generator[str, None, None]:
        url = self._ollama_url() + "/api/chat"
        try:
            with requests.post(
                url,
                json={
                    "model": self._ollama_model(),
                    "messages": messages,
                    "stream": True,
                    "options": {"num_predict": max_tokens, "temperature": 0.3},
                },
                stream=True,
                timeout=TIMEOUTS["ollama"],
            ) as resp:
                resp.raise_for_status()
                import json
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8", errors="ignore"))
                        text = chunk.get("message", {}).get("content", "")
                        if text:
                            yield text
                        if chunk.get("done"):
                            break
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Ollama stream indisponível: %s", e)


# ── Cache simples com TTL ─────────────────────────────────────────────

class _TTLCache:
    def __init__(self, ttl: int = 300):
        self._ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry and time.monotonic() - entry[0] < self._ttl:
            return entry[1]
        return None

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._store.clear()


_weather_cache = _TTLCache(ttl=600)    # 10 min
_finance_cache = _TTLCache(ttl=120)    # 2 min
_search_cache  = _TTLCache(ttl=300)    # 5 min


def cached_get(cache: _TTLCache, key: str, fn):
    """Retorna cache hit ou chama fn() e armazena o resultado."""
    hit = cache.get(key)
    if hit is not None:
        logger.debug("Cache hit: %s", key[:60])
        return hit
    result = fn()
    if result:
        cache.set(key, result)
    return result


# ── Truncagem de contexto ─────────────────────────────────────────────

def _truncate_messages(messages: list[dict], max_chars: int = 24_000) -> list[dict]:
    """
    Trunca as mensagens mais antigas se o total de caracteres exceder max_chars.
    Preserva sempre a mensagem de sistema e as 2 últimas mensagens.
    """
    total = sum(len(m.get("content") or "") for m in messages)
    if total <= max_chars:
        return messages

    system = [m for m in messages if m.get("role") == "system"]
    others = [m for m in messages if m.get("role") != "system"]

    # Preserva as 2 últimas (comando atual + contexto imediato)
    tail = others[-2:] if len(others) >= 2 else others
    head = others[:-2] if len(others) >= 2 else []

    # Remove do início até caber
    while head and sum(len(m.get("content") or "") for m in system + head + tail) > max_chars:
        head.pop(0)

    truncated = system + head + tail
    logger.debug("Contexto truncado: %d → %d chars",
                 total, sum(len(m.get("content") or "") for m in truncated))
    return truncated


# ── Observabilidade ───────────────────────────────────────────────────

def _emit_metric(provider: str, latency_s: float, usage: dict) -> None:
    """Registra métrica de chamada LLM. Não bloqueia; falhas são silenciosas."""
    try:
        from core.telemetry import record_llm_call
        record_llm_call(
            provider=provider,
            latency_s=latency_s,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
    except Exception:
        pass


# ── Instância global (lazy) ───────────────────────────────────────────

_client: Optional[LLMClient] = None


def get_client(config=None) -> LLMClient:
    """Retorna a instância compartilhada do LLMClient."""
    global _client
    if _client is None:
        if config is None:
            from core.config import Config
            config = Config()
        _client = LLMClient(config)
    return _client
