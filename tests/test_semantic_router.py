"""Testes para o cache semântico de roteamento (modules/semantic_router.py)."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules import semantic_router


def _fake_embed(text):
    """Embedding determinístico = contagem de letras (strings parecidas ~ vetores parecidos)."""
    text = (text or "").lower()
    return [float(text.count(c)) for c in "abcdefghijklmnopqrstuvwxyz "]


@pytest.fixture
def fresh_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_router, "DB_PATH", Path(tmp_path) / "sem.db")
    monkeypatch.setattr(semantic_router, "_initialized", False)
    monkeypatch.setattr(semantic_router, "_embed", _fake_embed)
    monkeypatch.setattr(
        "modules.tools.known_tools",
        lambda: {"get_time", "control_media", "open_application"},
    )
    return tmp_path


def test_remember_and_recall(fresh_cache):
    semantic_router.remember("que horas são agora", [{"name": "get_time", "arguments": {}}])
    calls = semantic_router.recall("que horas são agora")
    assert calls and calls[0]["name"] == "get_time"


def test_empty_cache_returns_none(fresh_cache):
    assert semantic_router.recall("qualquer coisa") is None


def test_slot_guard_blocks_wrong_argument(fresh_cache):
    semantic_router.remember(
        "toca coldplay",
        [{"name": "control_media", "arguments": {"action": "play", "query": "coldplay"}}],
    )
    # Paráfrase com OUTRO slot não pode reaproveitar o "coldplay" cacheado.
    assert semantic_router.recall("toca queen") is None
    # Paráfrase que contém o mesmo slot pode reaproveitar.
    calls = semantic_router.recall("bota coldplay")
    assert calls and calls[0]["arguments"]["query"] == "coldplay"


def test_unknown_tool_is_ignored(fresh_cache):
    semantic_router.remember("faz algo estranho", [{"name": "ferramenta_inexistente", "arguments": {}}])
    assert semantic_router.recall("faz algo estranho") is None


def test_disabled_is_noop(fresh_cache, monkeypatch):
    monkeypatch.setattr(semantic_router, "_enabled", lambda: False)
    semantic_router.remember("que horas são", [{"name": "get_time", "arguments": {}}])
    assert semantic_router.recall("que horas são") is None
