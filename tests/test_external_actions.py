"""Política de saída externa: fail-closed e dados mascarados."""

from modules import external_actions


class _Config:
    def __init__(self, mode="simulate", enabled=False):
        self.values = {
            "external_actions.mode": mode,
            "external_actions.live_enabled": enabled,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)


def test_external_actions_default_to_simulation(monkeypatch):
    monkeypatch.delenv(external_actions.LIVE_ENV_VAR, raising=False)
    assert external_actions.live_enabled(_Config()) is False


def test_live_requires_all_three_independent_locks(monkeypatch):
    monkeypatch.setenv(external_actions.LIVE_ENV_VAR, external_actions.LIVE_ENV_TOKEN)
    assert external_actions.live_enabled(_Config(mode="simulate", enabled=True)) is False
    assert external_actions.live_enabled(_Config(mode="live", enabled=False)) is False
    assert external_actions.live_enabled(_Config(mode="live", enabled=True)) is True


def test_wrong_environment_phrase_fails_closed(monkeypatch):
    monkeypatch.setenv(external_actions.LIVE_ENV_VAR, "sim")
    assert external_actions.live_enabled(_Config(mode="live", enabled=True)) is False


def test_recipient_masking_hides_phone_and_multiple_emails():
    assert external_actions.mask_recipient("+55 11 99999-1234") == "***1234"
    masked = external_actions.mask_recipient("alice@example.com, bob@example.org")
    assert masked == "a***@example.com, b***@example.org"
    assert "alice" not in masked and "bob" not in masked


def test_simulation_result_is_explicit():
    result = external_actions.simulation_result("WhatsApp", "+5511999991234")
    assert "SIMULAÇÃO" in result
    assert "Nada foi enviado" in result
    assert "+5511999991234" not in result
