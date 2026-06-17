"""Testes para o briefing diário proativo (modules/briefing.py)."""

from modules import briefing


def test_generate_combines_all_sections(monkeypatch):
    monkeypatch.setattr("modules.weather.get_weather", lambda loc="": "Ensolarado, 25°C")
    monkeypatch.setattr("modules.calendar_integration.get_today_events", lambda: "Agenda: reunião às 10h")
    monkeypatch.setattr("modules.reminders.list_reminders", lambda: "Lembretes pendentes: nenhum")
    monkeypatch.setattr("modules.productivity.show_usage", lambda: "Uso de apps: code 2h")

    text = briefing.generate()

    assert "Ensolarado" in text
    assert "reunião às 10h" in text
    assert "Lembretes pendentes" in text
    assert "Uso de apps" in text


def test_generate_skips_section_on_error(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("sem rede")

    monkeypatch.setattr("modules.weather.get_weather", boom)
    monkeypatch.setattr("modules.calendar_integration.get_today_events", lambda: "Agenda vazia")
    monkeypatch.setattr("modules.reminders.list_reminders", lambda: "Nenhum lembrete")
    monkeypatch.setattr("modules.productivity.show_usage", lambda: "Sem dados")

    text = briefing.generate()

    assert "Agenda vazia" in text
    assert "Nenhum lembrete" in text


def test_fire_briefing_does_not_raise_without_optional_deps(monkeypatch):
    monkeypatch.setattr(briefing, "generate", lambda: "briefing de teste")
    briefing._fire_briefing()
