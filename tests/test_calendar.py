"""Testes para consultas do Google Calendar."""

from datetime import datetime, timedelta

from modules import calendar_integration as calendar


class _Events:
    def __init__(self):
        self.params = None
        self.inserted_body = None

    def list(self, **kwargs):
        self.params = kwargs
        return self

    def insert(self, calendarId, body):
        self.inserted_body = body
        return self

    def execute(self):
        if self.inserted_body is not None:
            return {"summary": self.inserted_body["summary"]}
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


# ── create_event (args estruturados — usado pelo loop agentivo) ───────

def test_create_event_with_structured_args(monkeypatch):
    service = _Service()
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    result = calendar.create_event("Reunião sobre projeto novo", "amanhã", "15:00")

    body = service._events.inserted_body
    start = datetime.fromisoformat(body["start"]["dateTime"])
    assert start.hour == 15 and start.minute == 0
    assert body["start"]["timeZone"] == "America/Sao_Paulo"
    assert "Reunião sobre projeto novo" in result
    assert "Evento criado" in result


def test_create_event_defaults_to_9am_on_invalid_time(monkeypatch):
    service = _Service()
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    calendar.create_event("Evento", "hoje", "horário inválido")

    body = service._events.inserted_body
    start = datetime.fromisoformat(body["start"]["dateTime"])
    assert start.hour == 9 and start.minute == 0


def test_create_event_returns_dependency_error_without_service(monkeypatch):
    def _raise():
        raise RuntimeError("Instale: pip install google-api-python-client google-auth-oauthlib")
    monkeypatch.setattr(calendar, "_get_service", _raise)

    result = calendar.create_event("Reunião", "amanhã", "15:00")
    assert "Instale" in result


# ── _resolve_day ────────────────────────────────────────────────────

def test_resolve_day_hoje():
    now = datetime(2026, 6, 15, 10, 0)
    assert calendar._resolve_day("hoje", now) == now


def test_resolve_day_amanha():
    now = datetime(2026, 6, 15, 10, 0)
    assert calendar._resolve_day("amanhã", now) == now + timedelta(days=1)


def test_resolve_day_iso_date():
    now = datetime(2026, 6, 15, 10, 0)
    resolved = calendar._resolve_day("2026-07-01", now)
    assert resolved.year == 2026 and resolved.month == 7 and resolved.day == 1


def test_resolve_day_unrecognized_falls_back_to_tomorrow():
    now = datetime(2026, 6, 15, 10, 0)
    assert calendar._resolve_day("sexta-feira", now) == now + timedelta(days=1)


# ── add_event continua funcionando após o refactor para _insert_event ──

def test_add_event_still_creates_via_shared_helper(monkeypatch):
    service = _Service()
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    result = calendar.add_event("reunião amanhã às 14h sobre orçamento")

    body = service._events.inserted_body
    start = datetime.fromisoformat(body["start"]["dateTime"])
    assert start.hour == 14 and start.minute == 0
    assert "Evento criado" in result
