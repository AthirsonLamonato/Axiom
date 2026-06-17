"""Testes para o registro da ferramenta send_whatsapp_message no ToolRegistry."""

from modules import tools


def test_send_whatsapp_message_requires_confirmation():
    assert tools.needs_confirmation("send_whatsapp_message") is True


def test_send_whatsapp_message_is_high_risk():
    assert tools.get_risk("send_whatsapp_message") == "high"


def test_validate_rejects_missing_message():
    model, error = tools.validate("send_whatsapp_message", {"contact": "fulano"})
    assert model is None
    assert "message" in error.lower() or "args inválidos" in error.lower()


def test_validate_accepts_valid_args():
    model, error = tools.validate(
        "send_whatsapp_message", {"contact": "fulano", "message": "oi"}
    )
    assert error == ""
    assert model.contact == "fulano"
    assert model.message == "oi"


def test_execute_delegates_to_whatsapp_module(monkeypatch):
    captured = {}

    def fake_send(contact, message):
        captured["contact"] = contact
        captured["message"] = message
        return "ok"

    monkeypatch.setattr("modules.whatsapp.send", fake_send)
    model, _ = tools.validate("send_whatsapp_message", {"contact": "fulano", "message": "oi"})
    result = tools.execute("send_whatsapp_message", model)

    assert result == "ok"
    assert captured == {"contact": "fulano", "message": "oi"}
