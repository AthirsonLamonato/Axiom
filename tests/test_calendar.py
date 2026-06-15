"""Testes para consultas do Google Calendar."""

from datetime import datetime

from modules import calendar_integration as calendar


class _Events:
    def __init__(self):
        self.params = None

    def list(self, **kwargs):
        self.params = kwargs
        return self

    def execute(self):
        return {"items": []}


class _Service:
    def __init__(self):
        self._events = _Events()

    def events(self):
        return self._events


class _Config:
    def get(self, key, default=None):
        if key == "calendar.timezone":
            return "America/Sao_Paulo"
        return default


def test_get_day_events_uses_tomorrow_and_configured_timezone(monkeypatch):
    service = _Service()
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    result = calendar.get_day_events("amanhã")

    start = datetime.fromisoformat(service._events.params["timeMin"])
    end = datetime.fromisoformat(service._events.params["timeMax"])
    assert start.tzinfo is not None
    assert start.utcoffset().total_seconds() == -3 * 3600
    assert end - start == calendar.timedelta(days=1)
    assert "amanhã" in result
