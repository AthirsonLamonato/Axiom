"""Testes para timers de produtividade."""

from datetime import datetime, timedelta

from modules import productivity


def test_focus_start_hours_converts_to_minutes(monkeypatch):
    captured = {}

    def fake_focus_start(minutes):
        captured["minutes"] = minutes
        return "ok"

    monkeypatch.setattr(productivity, "focus_start", fake_focus_start)
    assert productivity.focus_start_hours("2") == "ok"
    assert captured["minutes"] == "120"


def test_pomodoro_restores_pending_state(tmp_path, monkeypatch):
    state = tmp_path / "pomodoro.json"
    monkeypatch.setattr(productivity, "POMODORO_STATE_PATH", state)
    monkeypatch.setattr(productivity, "_pomodoro", None)
    state.write_text(
        '{"minutes":25,"end_at":"' + (datetime.now() + timedelta(minutes=20)).isoformat() + '"}',
        encoding="utf-8",
    )

    result = productivity.focus_status()

    assert "restantes" in result
    productivity.focus_stop()


def test_pomodoro_discards_expired_state(tmp_path, monkeypatch):
    state = tmp_path / "pomodoro.json"
    monkeypatch.setattr(productivity, "POMODORO_STATE_PATH", state)
    monkeypatch.setattr(productivity, "_pomodoro", None)
    state.write_text(
        '{"minutes":25,"end_at":"' + (datetime.now() - timedelta(minutes=1)).isoformat() + '"}',
        encoding="utf-8",
    )
    assert productivity.focus_status() == "Nenhum timer ativo."
    assert not state.exists()
