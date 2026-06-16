"""
tests/test_embeddings.py — Testes unitários do core/embeddings.py

Tudo aqui é offline/mockado: nenhum teste depende de rede, chave real do
Gemini ou Ollama rodando.
"""

import pytest

import core.embeddings as emb


class _FakeConfig:
    def __init__(self, data: dict | None = None):
        self._data = data or {}

    def get(self, key, default=None):
        return self._data.get(key, default)


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200, raise_exc=None):
        self._json_data = json_data or {}
        self.status_code = status_code
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc

    def json(self):
        return self._json_data


class _FakeSession:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._exc:
            raise self._exc
        return self._response


@pytest.fixture(autouse=True)
def _reset_state():
    emb._embed_failures = 0
    emb._embed_open_until = 0.0
    emb._embed_cache.clear()
    yield
    emb._embed_failures = 0
    emb._embed_open_until = 0.0
    emb._embed_cache.clear()


# ── Circuit breaker próprio (não deve afetar/ser afetado pelo do Groq) ──

def test_embed_circuit_breaker_opens_after_threshold():
    assert not emb._embed_circuit_is_open()
    for _ in range(emb._EMBED_CB_THRESHOLD):
        emb._record_embed_failure()
    assert emb._embed_circuit_is_open()


def test_embed_circuit_breaker_resets_on_success():
    emb._record_embed_failure()
    emb._record_embed_failure()
    assert emb._embed_failures == 2
    emb._record_embed_success()
    assert emb._embed_failures == 0
    assert not emb._embed_circuit_is_open()


def test_embed_circuit_breaker_independent_from_groq_circuit():
    import core.providers as p
    p._groq_failures = 0
    p._groq_open_until = 0.0
    for _ in range(emb._EMBED_CB_THRESHOLD):
        emb._record_embed_failure()
    assert emb._embed_circuit_is_open()
    assert not p._circuit_is_open()  # circuito do Groq não foi afetado
    p._groq_failures = 0
    p._groq_open_until = 0.0


# ── pack/unpack ───────────────────────────────────────────────────────

def test_pack_unpack_roundtrip_exact():
    vec = [0.1, -0.5, 3.25, 0.0, -1.0]
    packed = emb.pack_embedding(vec)
    restored = emb.unpack_embedding(packed)
    assert len(restored) == len(vec)
    for a, b in zip(vec, restored):
        assert abs(a - b) < 1e-6


# ── cosine_similarity ────────────────────────────────────────────────

def test_cosine_similarity_identical_vectors():
    v = [1.0, 2.0, 3.0]
    assert abs(emb.cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_vectors():
    assert emb.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_is_safe():
    assert emb.cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
    assert emb.cosine_similarity([], []) == 0.0


def test_cosine_similarity_mismatched_length_is_safe():
    assert emb.cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


# ── embed_text: provider "none" e ausência de configuração ────────────

def test_embed_text_returns_none_when_provider_none():
    config = _FakeConfig({"ai.embeddings_provider": "none"})
    assert emb.embed_text("qualquer coisa", config) is None


def test_embed_text_returns_none_without_key_or_ollama(monkeypatch):
    # auto, sem GEMINI_API_KEY e sem Ollama alcançável
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(emb, "_get_session", lambda: _FakeSession(exc=ConnectionError("sem rede")))
    config = _FakeConfig({"ai.embeddings_provider": "auto"})
    assert emb.embed_text("qualquer coisa", config) is None


def test_embed_text_returns_none_for_blank_text():
    config = _FakeConfig({"ai.embeddings_provider": "gemini"})
    assert emb.embed_text("", config) is None
    assert emb.embed_text("   ", config) is None


# ── Gemini backend ──────────────────────────────────────────────────

def test_gemini_embed_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    fake_resp = _FakeResponse(json_data={"embedding": {"values": [0.1, 0.2, 0.3]}})
    monkeypatch.setattr(emb, "_get_session", lambda: _FakeSession(response=fake_resp))
    config = _FakeConfig({"ai.embeddings_provider": "gemini"})
    vec = emb.embed_text("oi", config)
    assert vec == [0.1, 0.2, 0.3]


def test_gemini_embed_without_key_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config = _FakeConfig({"ai.embeddings_provider": "gemini"})
    assert emb.embed_text("oi", config) is None


def test_gemini_embed_http_failure_returns_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(emb, "_get_session", lambda: _FakeSession(exc=TimeoutError("timeout")))
    config = _FakeConfig({"ai.embeddings_provider": "gemini"})
    assert emb.embed_text("oi", config) is None


# ── Ollama backend ──────────────────────────────────────────────────

def test_ollama_embed_success(monkeypatch):
    fake_resp = _FakeResponse(json_data={"embedding": [0.4, 0.5]})
    monkeypatch.setattr(emb, "_get_session", lambda: _FakeSession(response=fake_resp))
    config = _FakeConfig({"ai.embeddings_provider": "ollama"})
    vec = emb.embed_text("oi", config)
    assert vec == [0.4, 0.5]


def test_ollama_embed_failure_returns_none(monkeypatch):
    monkeypatch.setattr(emb, "_get_session", lambda: _FakeSession(exc=ConnectionError("offline")))
    config = _FakeConfig({"ai.embeddings_provider": "ollama"})
    assert emb.embed_text("oi", config) is None


# ── auto: prioriza Gemini se houver chave, senão Ollama ───────────────

def test_auto_prefers_gemini_when_key_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    fake_resp = _FakeResponse(json_data={"embedding": {"values": [0.9]}})
    session = _FakeSession(response=fake_resp)
    monkeypatch.setattr(emb, "_get_session", lambda: session)
    config = _FakeConfig({"ai.embeddings_provider": "auto"})
    vec = emb.embed_text("oi", config)
    assert vec == [0.9]


def test_auto_falls_back_to_ollama_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake_resp = _FakeResponse(json_data={"embedding": [0.7]})
    monkeypatch.setattr(emb, "_get_session", lambda: _FakeSession(response=fake_resp))
    config = _FakeConfig({"ai.embeddings_provider": "auto"})
    vec = emb.embed_text("oi", config)
    assert vec == [0.7]


# ── cache ────────────────────────────────────────────────────────────

def test_embed_text_uses_cache_on_repeated_call(monkeypatch):
    fake_resp = _FakeResponse(json_data={"embedding": [0.1]})
    session = _FakeSession(response=fake_resp)
    monkeypatch.setattr(emb, "_get_session", lambda: session)
    config = _FakeConfig({"ai.embeddings_provider": "ollama"})
    emb.embed_text("repete", config)
    emb.embed_text("repete", config)
    assert len(session.calls) == 1  # segunda chamada veio do cache
