"""Testes para consultas do Google Calendar."""

from datetime import datetime, timedelta

from modules import calendar_integration as calendar


class _Events:
    def __init__(self, list_items=None):
        self.params = None
        self.inserted_body = None
        self.deleted_event_id = None
        self.deleted_send_updates = None
        self._list_items = list_items if list_items is not None else []

    def list(self, **kwargs):
        self.params = kwargs
        return self

    def insert(self, calendarId, body, sendUpdates="none"):
        self.inserted_body = body
        self.send_updates = sendUpdates
        return self

    def delete(self, calendarId, eventId, sendUpdates="none"):
        self.deleted_event_id = eventId
        self.deleted_send_updates = sendUpdates
        return self

    def patch(self, calendarId, eventId, body, sendUpdates="none"):
        self.patched_event_id = eventId
        self.patched_body = body
        self.patched_send_updates = sendUpdates
        return self

    def execute(self):
        if getattr(self, "patched_event_id", None) is not None:
            return dict(self.patched_body)  # simula o Google ecoando os campos atualizados
        if self.deleted_event_id is not None:
            return {}
        if self.inserted_body is not None:
            return {"summary": self.inserted_body["summary"]}
        return {"items": self._list_items}


class _Service:
    def __init__(self, list_items=None):
        self._events = _Events(list_items=list_items)

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


def test_create_event_preserves_internal_capitalization(monkeypatch):
    """Regressão: .capitalize() forçava todo o título pra minúsculo,
    destruindo siglas/nomes próprios como '[TESTE] Reunião com a Paçoca'."""
    service = _Service()
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    calendar.create_event("[TESTE] Reunião com a Paçoca", "amanhã", "10:00")

    assert service._events.inserted_body["summary"] == "[TESTE] Reunião com a Paçoca"


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
    assert "attendees" not in body  # sem e-mail no comando → sem convidados


# ── attendees (convidados) ─────────────────────────────────────────

def test_add_event_extracts_emails_as_attendees(monkeypatch):
    service = _Service()
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())
    monkeypatch.setattr(calendar, "_external_live_enabled", lambda: True)

    result = calendar.add_event("reunião amanhã às 14h com a@x.com e b@y.com")

    body = service._events.inserted_body
    emails = {a["email"] for a in body["attendees"]}
    assert emails == {"a@x.com", "b@y.com"}
    assert service._events.send_updates == "all"
    assert "a@x.com" not in body["summary"]  # e-mails não vazam pro título
    assert "convidados" in result.lower()


def test_create_event_with_attendees_sends_invite(monkeypatch):
    service = _Service()
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())
    monkeypatch.setattr(calendar, "_external_live_enabled", lambda: True)

    calendar.create_event("Reunião", "amanhã", "15:00", attendees=["a@x.com", "b@y.com"])

    body = service._events.inserted_body
    assert body["attendees"] == [{"email": "a@x.com"}, {"email": "b@y.com"}]
    assert service._events.send_updates == "all"


def test_create_event_without_attendees_does_not_send_updates(monkeypatch):
    service = _Service()
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    calendar.create_event("Reunião", "amanhã", "15:00")

    body = service._events.inserted_body
    assert "attendees" not in body
    assert service._events.send_updates == "none"


def test_create_event_with_attendees_simulates_without_opening_service(monkeypatch):
    monkeypatch.setattr(calendar, "_external_live_enabled", lambda: False)
    monkeypatch.setattr(
        calendar,
        "_get_service",
        lambda: (_ for _ in ()).throw(AssertionError("serviço externo não deve abrir")),
    )

    result = calendar.create_event(
        "Reunião", "amanhã", "15:00", attendees=["alice@example.com"]
    )

    assert "SIMULAÇÃO" in result
    assert "Nada foi enviado" in result
    assert "alice@example.com" not in result


# ── delete_event ────────────────────────────────────────────────────

def test_delete_event_deletes_unique_match(monkeypatch):
    items = [{"id": "evt1", "summary": "[TESTE v3] Reunião", "start": {"dateTime": "2026-06-17T16:00:00-03:00"}}]
    service = _Service(list_items=items)
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    result = calendar.delete_event("TESTE v3")

    assert service._events.deleted_event_id == "evt1"
    assert service._events.deleted_send_updates == "none"
    assert "apagado" in result.lower()


def test_delete_event_sends_updates_when_attendees_present(monkeypatch):
    items = [{
        "id": "evt1", "summary": "[TESTE v3] Reunião",
        "start": {"dateTime": "2026-06-17T16:00:00-03:00"},
        "attendees": [{"email": "a@x.com"}],
    }]
    service = _Service(list_items=items)
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())
    monkeypatch.setattr(calendar, "_external_live_enabled", lambda: True)

    calendar.delete_event("TESTE v3")

    assert service._events.deleted_send_updates == "all"


def test_delete_event_with_attendees_is_blocked_in_simulation(monkeypatch):
    items = [{
        "id": "evt1", "summary": "Reunião externa",
        "start": {"dateTime": "2026-06-17T16:00:00-03:00"},
        "attendees": [{"email": "alice@example.com"}],
    }]
    service = _Service(list_items=items)
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())
    monkeypatch.setattr(calendar, "_external_live_enabled", lambda: False)

    result = calendar.delete_event("Reunião externa")

    assert service._events.deleted_event_id is None
    assert "SIMULAÇÃO" in result
    assert "alice@example.com" not in result


def test_delete_event_multiple_matches_does_not_delete(monkeypatch):
    items = [
        {"id": "evt1", "summary": "[TESTE] Reunião A", "start": {"dateTime": "2026-06-17T16:00:00-03:00"}},
        {"id": "evt2", "summary": "[TESTE] Reunião B", "start": {"dateTime": "2026-06-18T10:00:00-03:00"}},
    ]
    service = _Service(list_items=items)
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    result = calendar.delete_event("TESTE")

    assert service._events.deleted_event_id is None  # nada apagado
    assert "Reunião A" in result and "Reunião B" in result
    assert "específico" in result.lower()


def test_delete_event_no_match_returns_not_found(monkeypatch):
    service = _Service(list_items=[])
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    result = calendar.delete_event("Reunião inexistente")

    assert service._events.deleted_event_id is None
    assert "não encontrei" in result.lower()


def test_delete_event_requires_title():
    assert "título" in calendar.delete_event("").lower()
    assert "título" in calendar.delete_event("   ").lower()


# ── update_event ────────────────────────────────────────────────────

def test_update_event_changes_time(monkeypatch):
    items = [{
        "id": "evt1", "summary": "[TESTE] Reunião",
        "start": {"dateTime": "2026-06-17T16:00:00-03:00"},
        "end": {"dateTime": "2026-06-17T17:00:00-03:00"},
    }]
    service = _Service(list_items=items)
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    result = calendar.update_event("TESTE", new_time="18:00")

    body = service._events.patched_body
    new_start = datetime.fromisoformat(body["start"]["dateTime"])
    new_end = datetime.fromisoformat(body["end"]["dateTime"])
    assert new_start.hour == 18 and new_start.minute == 0
    assert (new_end - new_start) == timedelta(hours=1)  # duração preservada
    assert "atualizado" in result.lower()


def test_update_event_changes_title(monkeypatch):
    items = [{
        "id": "evt1", "summary": "[TESTE] Reunião",
        "start": {"dateTime": "2026-06-17T16:00:00-03:00"},
        "end": {"dateTime": "2026-06-17T17:00:00-03:00"},
    }]
    service = _Service(list_items=items)
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    calendar.update_event("TESTE", new_title="Novo título")

    assert service._events.patched_body["summary"] == "Novo título"


def test_update_event_requires_at_least_one_change(monkeypatch):
    service = _Service(list_items=[])
    monkeypatch.setattr(calendar, "_get_service", lambda: service)

    result = calendar.update_event("TESTE")

    assert "pelo menos uma mudança" in result.lower()
    assert getattr(service._events, "patched_event_id", None) is None


def test_update_event_multiple_matches_does_not_update(monkeypatch):
    items = [
        {"id": "evt1", "summary": "[TESTE] A", "start": {"dateTime": "2026-06-17T16:00:00-03:00"}},
        {"id": "evt2", "summary": "[TESTE] B", "start": {"dateTime": "2026-06-18T10:00:00-03:00"}},
    ]
    service = _Service(list_items=items)
    monkeypatch.setattr(calendar, "_get_service", lambda: service)
    monkeypatch.setattr(calendar, "_get_config", lambda: _Config())

    result = calendar.update_event("TESTE", new_time="10:00")

    assert getattr(service._events, "patched_event_id", None) is None
    assert "específico" in result.lower()


def test_update_event_requires_title():
    assert "título" in calendar.update_event("", new_time="10:00").lower()
