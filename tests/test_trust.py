"""Testes para o aprendizado de confiança em confirmações (modules/trust.py)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import storage.memory as memory
from modules import trust


@pytest.fixture
def fresh_mem(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "mem.db"))
    memory.init()
    return tmp_path


def test_trusts_after_threshold(fresh_mem, monkeypatch):
    monkeypatch.setattr("modules.tools.get_risk", lambda n: "medium")
    assert trust.auto_approve("git_operation") is False
    for _ in range(3):
        trust.record("git_operation", True)
    assert trust.auto_approve("git_operation") is True


def test_denial_resets_trust(fresh_mem, monkeypatch):
    monkeypatch.setattr("modules.tools.get_risk", lambda n: "medium")
    for _ in range(3):
        trust.record("x", True)
    assert trust.auto_approve("x") is True
    trust.record("x", False)
    assert trust.auto_approve("x") is False


def test_high_risk_never_auto_approved(fresh_mem, monkeypatch):
    monkeypatch.setattr("modules.tools.get_risk", lambda n: "high")
    for _ in range(10):
        trust.record("send_whatsapp_message", True)
    assert trust.auto_approve("send_whatsapp_message") is False


def test_disabled_never_trusts(fresh_mem, monkeypatch):
    monkeypatch.setattr("modules.tools.get_risk", lambda n: "medium")
    monkeypatch.setattr(trust, "_is_enabled", lambda: False)
    for _ in range(5):
        trust.record("git_operation", True)
    assert trust.auto_approve("git_operation") is False
