"""
tests/test_providers.py — Testes unitários e de integração do core/providers.py

Unitários (rodam sempre):
  - Circuit breaker: abertura, reset, estado
  - TTL cache: hit/miss/expiração
  - _truncate_messages: preserva sistema + tail; conta tool_calls
  - _msg_chars: content + tool_calls

Integração (requer GROQ_API_KEY e/ou Ollama rodando):
  - Marcados com @pytest.mark.integration
  - Rode com: pytest -m integration tests/test_providers.py
"""

import time
import pytest


# ── Unit: circuit breaker ────────────────────────────────────────────


def _reset_cb():
    import core.providers as p
    p._groq_failures = 0
    p._groq_open_until = 0.0


def test_circuit_breaker_opens_after_threshold():
    import core.providers as p
    _reset_cb()
    assert not p._circuit_is_open()
    for _ in range(p._CB_THRESHOLD):
        p._record_groq_failure()
    assert p._circuit_is_open()
    _reset_cb()


def test_circuit_breaker_resets_on_success():
    import core.providers as p
    _reset_cb()
    p._record_groq_failure()
    p._record_groq_failure()
    assert p._groq_failures == 2
    p._record_groq_success()
    assert p._groq_failures == 0
    assert not p._circuit_is_open()


def test_circuit_breaker_below_threshold_does_not_open():
    import core.providers as p
    _reset_cb()
    for _ in range(p._CB_THRESHOLD - 1):
        p._record_groq_failure()
    assert not p._circuit_is_open()
    _reset_cb()


# ── Unit: _is_tool_use_failed ──────────────────────────────────────────

def test_is_tool_use_failed_detects_groq_400():
    import core.providers as p
    exc = RuntimeError("400 Bad Request")
    fake_resp = type("R", (), {"text": '{"error":{"code":"tool_use_failed"}}'})()
    exc.response = fake_resp
    assert p._is_tool_use_failed(exc) is True


def test_is_tool_use_failed_false_for_other_errors():
    import core.providers as p
    assert p._is_tool_use_failed(RuntimeError("conexão recusada")) is False

    exc = RuntimeError("401 Unauthorized")
    fake_resp = type("R", (), {"text": '{"error":{"code":"invalid_api_key"}}'})()
    exc.response = fake_resp
    assert p._is_tool_use_failed(exc) is False


def test_tool_use_failed_does_not_count_toward_circuit_breaker(monkeypatch):
    """tool_use_failed é falha de formatação do modelo, não indisponibilidade
    real do Groq — não deve abrir o circuit breaker."""
    import core.providers as p
    _reset_cb()

    client = p.LLMClient(config=type("C", (), {"get": lambda self, k, d=None: d})())
    monkeypatch.setattr(client, "_get_groq_key", lambda: "fake-key")
    monkeypatch.setattr(client, "_groq_model", lambda: "llama-3.3-70b-versatile")

    class _FakeResp:
        status_code = 400
        text = '{"error":{"code":"tool_use_failed"}}'

        def raise_for_status(self):
            import requests
            err = requests.HTTPError("400 Client Error")
            err.response = self
            raise err

    monkeypatch.setattr(p, "_get_session", lambda: type(
        "S", (), {"post": lambda self, *a, **k: _FakeResp()}
    )())
    monkeypatch.setattr(p, "_retry_http", lambda fn, **k: fn())

    with pytest.raises(Exception):
        client._groq_raw([{"role": "user", "content": "oi"}])

    assert p._groq_failures == 0
    assert not p._circuit_is_open()
    _reset_cb()


# ── Unit: TTL cache ──────────────────────────────────────────────────


def test_ttl_cache_miss_returns_none():
    from core.providers import _TTLCache
    cache = _TTLCache(ttl=60)
    assert cache.get("missing") is None


def test_ttl_cache_hit_returns_value():
    from core.providers import _TTLCache
    cache = _TTLCache(ttl=60)
    cache.set("k", "v")
    assert cache.get("k") == "v"


def test_ttl_cache_expires():
    from core.providers import _TTLCache
    cache = _TTLCache(ttl=0)  # TTL = 0 → expira imediatamente
    cache.set("k", "v")
    time.sleep(0.01)
    assert cache.get("k") is None


def test_ttl_cache_clear():
    from core.providers import _TTLCache
    cache = _TTLCache(ttl=60)
    cache.set("a", 1)
    cache.clear()
    assert cache.get("a") is None


# ── Unit: _msg_chars ─────────────────────────────────────────────────


def test_msg_chars_content_only():
    from core.providers import _msg_chars
    m = {"role": "user", "content": "hello world"}
    assert _msg_chars(m) == len("hello world")


def test_msg_chars_with_tool_calls():
    from core.providers import _msg_chars
    m = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "open_app", "arguments": '{"app":"code"}'}}],
    }
    chars = _msg_chars(m)
    assert chars > 0


def test_msg_chars_none_content():
    from core.providers import _msg_chars
    m = {"role": "assistant", "content": None}
    assert _msg_chars(m) == 0


# ── Unit: _truncate_messages ──────────────────────────────────────────


def test_truncate_preserves_short_context():
    from core.providers import _truncate_messages
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    result = _truncate_messages(msgs, max_chars=10_000)
    assert result == msgs


def test_truncate_removes_oldest_non_system():
    from core.providers import _truncate_messages
    sys_msg = {"role": "system", "content": "s" * 100}
    old = {"role": "user", "content": "x" * 10_000}
    recent1 = {"role": "user", "content": "recent1"}
    recent2 = {"role": "assistant", "content": "recent2"}
    msgs = [sys_msg, old, recent1, recent2]
    result = _truncate_messages(msgs, max_chars=1_000)
    assert sys_msg in result
    assert recent1 in result
    assert recent2 in result
    # O antigo deve ter sido removido
    assert old not in result


def test_truncate_always_preserves_system():
    from core.providers import _truncate_messages
    sys_msg = {"role": "system", "content": "s" * 5}
    msgs = [sys_msg] + [{"role": "user", "content": "x" * 5000} for _ in range(10)]
    result = _truncate_messages(msgs, max_chars=500)
    assert sys_msg in result


# ── Integration: Groq (requer GROQ_API_KEY) ──────────────────────────


@pytest.mark.integration
def test_groq_chat_returns_text():
    import os
    if not os.environ.get("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEY não configurada")
    from core.providers import get_client
    from core.config import Config
    client = get_client(Config())
    resp = client.chat([{"role": "user", "content": "responda apenas: ok"}], max_tokens=10)
    assert isinstance(resp, str)
    assert len(resp) > 0


@pytest.mark.integration
def test_groq_circuit_breaker_records_failure_on_bad_key():
    import os
    from unittest.mock import patch
    import core.providers as p
    _reset_cb()
    original_key = os.environ.get("GROQ_API_KEY", "")
    try:
        with patch.dict(os.environ, {"GROQ_API_KEY": "invalid-key-test"}):
            p._client = None  # força novo client com chave inválida
            client = p.get_client()
            client._groq_key = None
            try:
                client._groq_raw([{"role": "user", "content": "test"}], max_tokens=5)
            except Exception:
                pass
        assert p._groq_failures >= 1
    finally:
        _reset_cb()
        p._client = None
        if original_key:
            os.environ["GROQ_API_KEY"] = original_key
        elif "GROQ_API_KEY" in os.environ:
            del os.environ["GROQ_API_KEY"]


# ── Integration: Ollama (requer Ollama rodando em localhost:11434) ────


@pytest.mark.integration
def test_ollama_chat_returns_text():
    import requests
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        if not r.ok:
            pytest.skip("Ollama não está respondendo")
    except Exception:
        pytest.skip("Ollama não está acessível")

    from core.providers import get_client
    from core.config import Config
    client = get_client(Config())
    resp = client._ollama_chat([{"role": "user", "content": "responda apenas: ok"}], max_tokens=10)
    assert isinstance(resp, str)


# ── Unit: seleção local por padrão ─────────────────────────────────────

def test_chat_uses_ollama_by_default_without_reading_cloud_key(monkeypatch):
    import core.providers as p

    class Config:
        def get(self, key, default=None):
            return {"ai.provider": "ollama", "ai.model": "qwen3:4b"}.get(key, default)

    client = p.LLMClient(Config())
    calls = []
    monkeypatch.setattr(client, "_get_groq_key", lambda: (_ for _ in ()).throw(AssertionError("não deve ler chave")))
    monkeypatch.setattr(client, "_ollama_chat", lambda messages, max_tokens=1024: calls.append(messages) or "ok local")

    assert client.chat([{"role": "user", "content": "oi"}]) == "ok local"
    assert len(calls) == 1


def test_auto_only_uses_cloud_first_when_explicitly_enabled(monkeypatch):
    import core.providers as p

    class Config:
        def __init__(self, cloud_first):
            self.cloud_first = cloud_first
        def get(self, key, default=None):
            return {"ai.provider": "auto", "ai.cloud_first": self.cloud_first}.get(key, default)

    client = p.LLMClient(Config(False))
    monkeypatch.setattr(client, "_get_groq_key", lambda: (_ for _ in ()).throw(AssertionError("nuvem não deve ser consultada")))
    monkeypatch.setattr(client, "_ollama_chat", lambda messages, max_tokens=1024: "local")
    assert client.chat([{"role": "user", "content": "oi"}]) == "local"
