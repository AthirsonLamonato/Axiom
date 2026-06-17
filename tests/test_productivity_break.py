"""Testes para a sugestão proativa de pausa (modules/productivity.py)."""

import time

from modules import productivity


def _config_with(value):
    return type("C", (), {"get": lambda self, k, d=None: value})()


def test_take_break_resets_timer_and_flag():
    tracker = productivity.UsageTracker()
    tracker._break_notified = True
    tracker.take_break()
    assert tracker._break_notified is False
    assert time.monotonic() - tracker._last_break < 1


def test_check_break_suggestion_fires_after_threshold(monkeypatch):
    tracker = productivity.UsageTracker()
    monkeypatch.setattr("core.config.Config", lambda: _config_with(0.0001))
    tracker._last_break = time.monotonic() - 1  # 1s "atrás", já excede limiar minúsculo

    notified = []
    monkeypatch.setattr("output.notifier.notify", lambda title, msg: notified.append(msg))

    tracker._check_break_suggestion()

    assert tracker._break_notified is True
    assert notified and "pausa" in notified[0].lower()


def test_check_break_suggestion_does_not_refire(monkeypatch):
    tracker = productivity.UsageTracker()
    monkeypatch.setattr("core.config.Config", lambda: _config_with(0.0001))
    tracker._last_break = time.monotonic() - 1

    notified = []
    monkeypatch.setattr("output.notifier.notify", lambda title, msg: notified.append(msg))

    tracker._check_break_suggestion()
    tracker._check_break_suggestion()

    assert len(notified) == 1


def test_check_break_suggestion_disabled_when_zero(monkeypatch):
    tracker = productivity.UsageTracker()
    monkeypatch.setattr("core.config.Config", lambda: _config_with(0))
    tracker._last_break = time.monotonic() - 10000

    notified = []
    monkeypatch.setattr("output.notifier.notify", lambda title, msg: notified.append(msg))

    tracker._check_break_suggestion()

    assert notified == []


def test_take_break_command_resets_global_tracker(monkeypatch):
    fake_tracker = productivity.UsageTracker()
    fake_tracker._break_notified = True
    monkeypatch.setattr(productivity, "_tracker", fake_tracker)

    result = productivity.take_break()

    assert "Pausa registrada" in result
    assert fake_tracker._break_notified is False
