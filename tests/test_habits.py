"""Testes para o detector de hábitos (modules/habits.py)."""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules import habits


def _mk(raw, dt, success=1):
    return {"raw_input": raw, "ts": dt.isoformat(), "success": success}


def test_detects_recurring_habit(monkeypatch):
    data = [_mk("abre o vscode", datetime(2026, 6, 10 + i, 9, 5)) for i in range(4)]
    monkeypatch.setattr(habits, "_load_interactions", lambda limit=1000: data)
    found = habits.detect_habits(min_days=3)
    assert any("vscode" in h["signature"] for h in found)
    top = found[0]
    assert top["hour"] == 9
    assert top["days"] >= 3


def test_below_min_days_is_ignored(monkeypatch):
    data = [_mk("abre o vscode", datetime(2026, 6, 10 + i, 9, 0)) for i in range(2)]
    monkeypatch.setattr(habits, "_load_interactions", lambda limit=1000: data)
    assert habits.detect_habits(min_days=3) == []


def test_failed_interactions_excluded(monkeypatch):
    data = [_mk("abre o vscode", datetime(2026, 6, 10 + i, 9, 0), success=0) for i in range(5)]
    monkeypatch.setattr(habits, "_load_interactions", lambda limit=1000: data)
    assert habits.detect_habits(min_days=3) == []


def test_signature_strips_articles_and_numbers():
    assert habits._signature("abre o vscode") == "abre vscode"
    assert habits._signature("volume 60") == "volume"
