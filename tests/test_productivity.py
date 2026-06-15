"""Testes para timers de produtividade."""

from modules import productivity


def test_focus_start_hours_converts_to_minutes(monkeypatch):
    captured = {}

    def fake_focus_start(minutes):
        captured["minutes"] = minutes
        return "ok"

    monkeypatch.setattr(productivity, "focus_start", fake_focus_start)
    assert productivity.focus_start_hours("2") == "ok"
    assert captured["minutes"] == "120"
