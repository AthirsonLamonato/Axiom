"""
core/providers.py — Cliente HTTP centralizado para todos os provedores de IA

Funcionalidades:
  - Interface única: LLMClient.chat() → Groq (online) ou Ollama (local)
  - Retry com backoff exponencial para 429, 502, 503, timeouts
  - Circuit breaker: após N falhas Groq consecutivas, usa Ollama temporariamente
  - Logs sanitizados: API keys nunca aparecem em log
  - Métricas opcionais: latência, tokens, provedor usado
"""

import json
import logging
import random
import threading
import time
from typing import Any, Generator, Optional

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

# ── Configurações do circuit breaker ─────────────────────────────────
_CB_THRESHOLD = 3        # falhas consecutivas antes de abrir o circuito
_CB_RESET_SECS = 120     # segundos antes de testar Groq novamente

# Estado do circuit breaker (módulo-level — compartilhado no processo,
# mutado por threads concorrentes: dashboard web + loop de voz/texto)
_groq_failures: int = 0
_groq_open_until: float = 0.0
_circuit_lock = threading.Lock()

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

# ── Sessão HTTP compartilhada com connection pool ─────────────────────
_http_session: Optional[requests.Session] = None
_session_lock = threading.Lock()


def _get_session() -> requests.Session:
    global _http_session
    with _session_lock:
        if _http_session is None:
            _http_session = requests.Session()
            adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=0)
            _http_session.mount("https://", adapter)
            _http_session.mount("http://", adapter)
        return _http_session


# ── Helpers ───────────────────────────────────────────────────────────

def _redact_auth(headers: dict) -> dict:
    """Remove Authorization header value dos logs."""
    safe = dict(headers)
    if "Authorization" in safe:
        safe["Authorization"] = "Bearer ***"
    return safe


def _is_tool_use_failed(exc: Exception) -> bool:
    """
    True se a exceção é um 400 'tool_use_failed' do Groq — o modelo tentou
    chamar uma ferramenta mas formatou errado. É um problema de amostragem do
    modelo (frequentemente some ao tentar de novo o mesmo request), não uma
    indisponibilidade real do Groq — não deve contar para o circuit breaker.
    """
    resp = getattr(exc, "response", None)
    body = getattr(resp, "text", "") or ""
    return "tool_use_failed" in body


def _circuit_is_open() -> bool:
    with _circuit_lock:
        return time.monotonic() < _groq_open_until


def _record_groq_failure() -> None:
    global _groq_failures, _groq_open_until
    with _circuit_lock:
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
    with _circuit_lock:
        if _groq_failures > 0:
            logger.info("Circuit breaker FECHADO: Groq respondeu com sucesso.")
        _groq_failures = 0
        _groq_open_until = 0.0


def _retry_http(fn, *, max_attempts: int = 3, base_delay: float = 1.0) -> requests.Response:
    """
    Executa fn() com retry exponencial para erros recuperáveis.
    Recuperável: 429 (rate limit), 502/503 (server error), ConnectionError, Timeout.
    fn pode receber a sessão compartilhada via _get_session().
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
    Cliente de LLM local-first: Ollama como padrão, com Groq opcional e explícito.

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
        return self.config.get("ai.model", "qwen3:4b")

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
        Usa Ollama por padrão. Groq só é usado quando ai.provider=groq ou quando ai.provider=auto e ai.cloud_first=true.
        """
        if system:
            messages = [{"role": "system", "content": system}] + list(messages)

        # Trunca contexto muito longo antes de enviar
        messages = _truncate_messages(messages, max_chars=24_000)

        provider = self.config.get("ai.provider", "ollama")
        cloud_first = bool(self.config.get("ai.cloud_first", False))
        should_try_cloud = provider == "groq" or (provider == "auto" and cloud_first)
        groq_key = self._get_groq_key() if should_try_cloud else ""

        # Groq só é prioritário quando explicitamente escolhido.
        if (provider == "groq" or (provider == "auto" and cloud_first)) and groq_key and not _circuit_is_open():
            try:
                if stream:
                    return self._groq_stream(messages, tools, tool_choice, max_tokens)
                return self._groq_chat(messages, tools, tool_choice, max_tokens)
            except Exception as e:
                # _groq_raw() / _groq_stream() já registraram a falha — não duplicar
                logger.warning("Groq falhou (%s) — usando Ollama como fallback.", e)

        # Ollama é o caminho padrão e não exige chave nem custo de API.
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

        try:
            session = _get_session()
            resp = _retry_http(
                lambda: session.post(_GROQ_URL, headers=headers, json=body,
                                     timeout=TIMEOUTS["groq"]),
            )
            if resp.status_code == 401:
                self._groq_key = None
                raise RuntimeError("Groq 401 — verifique a GROQ_API_KEY.")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if not _is_tool_use_failed(e):
                _record_groq_failure()
            raise

        _record_groq_success()
        latency = time.monotonic() - t0
        usage = data.get("usage", {})
        logger.debug("Groq OK: %.2fs | tokens in=%s out=%s",
                     latency, usage.get("prompt_tokens", "?"), usage.get("completion_tokens", "?"))

        _emit_metric("groq", latency, usage)
        return data

    def _groq_chat(self, messages, tools=None, tool_choice=None, max_tokens=1024) -> str:
        data = self._groq_raw(messages, tools, tool_choice, max_tokens)
        return (data["choices"][0]["message"].get("content") or "").strip()

    def _groq_stream(self, messages, tools=None, tool_choice=None,
                     max_tokens=1024) -> Generator[str, None, None]:
        headers = self._groq_headers()
        body = self._groq_body(messages, tools, tool_choice, max_tokens, stream=True)
        _started = False  # True quando o primeiro chunk foi emitido
        try:
            session = _get_session()
            with session.post(_GROQ_STREAM_URL, headers=headers, json=body,
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
                        chunk = json.loads(raw)
                        delta = chunk["choices"][0].get("delta", {})
                        text = delta.get("content") or ""
                        if text:
                            _started = True
                            yield text
                    except Exception:
                        pass
        except Exception as e:
            _record_groq_failure()
            if _started:
                # Já emitimos chunks — não há como fazer fallback limpo
                logger.warning("Groq stream interrompido após início: %s", e)
            else:
                logger.info("Groq stream falhou antes do primeiro chunk — fallback Ollama: %s", e)
                yield from self._ollama_stream(messages, max_tokens)

    # ── Ollama ──────────────────────────────────────────────────────

    def _ollama_chat(self, messages: list[dict], max_tokens: int = 1024) -> str:
        url = self._ollama_url() + "/api/chat"
        try:
            session = _get_session()
            t0 = time.monotonic()
            resp = _retry_http(
                lambda: session.post(
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

def _msg_chars(m: dict) -> int:
    """Conta chars de uma mensagem incluindo content e tool_calls."""
    total = len(m.get("content") or "")
    for tc in m.get("tool_calls", []):
        total += len(json.dumps(tc.get("function", {}), ensure_ascii=False))
    return total


def _truncate_messages(messages: list[dict], max_chars: int = 24_000) -> list[dict]:
    """
    Trunca as mensagens mais antigas se o total de caracteres exceder max_chars.
    Estratégia em cascata:
      1. Remove mensagens antigas do head (preservando system + as 2 mais recentes).
      2. Se system + tail ainda excederem, distribui o orçamento disponível entre as
         tail messages (da mais antiga para a mais nova), truncando content se necessário.
    Garante que a saída SEMPRE cabe em max_chars.
    """
    total = sum(_msg_chars(m) for m in messages)
    if total <= max_chars:
        return messages

    system = [m for m in messages if m.get("role") == "system"]
    others = [m for m in messages if m.get("role") != "system"]

    tail = others[-2:] if len(others) >= 2 else list(others)
    head = others[:-2] if len(others) >= 2 else []

    # Passo 1: remove mensagens do head (sem truncar content)
    while head and sum(_msg_chars(m) for m in system + head + tail) > max_chars:
        head.pop(0)

    truncated = system + head + tail

    # Passo 2: se ainda excede, distribui orçamento pelo tail com truncagem de content
    if sum(_msg_chars(m) for m in truncated) > max_chars:
        sys_chars = sum(_msg_chars(m) for m in system)
        budget_tail = max_chars - sys_chars  # orçamento restante para as tail messages

        if budget_tail <= 0:
            # System sozinho excede — trunca system e tenta preservar a mensagem mais recente
            s = system[0] if system else None
            if not s:
                return tail[-1:] if tail else []
            content = s.get("content", "")
            tail_chars = _msg_chars(tail[-1]) if tail else 0
            sys_budget = max(0, max_chars - tail_chars)
            if sys_budget < 10:
                return tail[-1:] if tail else []
            return [{**s, "content": content[:sys_budget - 1] + "…"}] + (tail[-1:] if tail else [])

        # Distribui o orçamento do tail da mensagem mais antiga para a mais nova
        new_tail: list[dict] = []
        remaining = budget_tail
        for m in tail:
            mc = _msg_chars(m)
            if mc <= remaining:
                new_tail.append(m)
                remaining -= mc
            elif remaining > 20:
                content = m.get("content") or ""
                new_tail.append({**m, "content": content[:remaining - 1] + "…"})
                remaining = 0
            # else: descarta mensagem (sem espaço)

        truncated = system + new_tail

    logger.debug("Contexto truncado: %d → %d chars",
                 total, sum(_msg_chars(m) for m in truncated))
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
