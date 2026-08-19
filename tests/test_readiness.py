"""Testes do diagnóstico de prontidão."""

from core.readiness import Check, _check_wakeword, _check_whisper, format_report


def test_report_marks_required_failure():
    report = format_report([
        Check("IA", False, True, "ausente", "instale"),
        Check("Opcional", False, False, "ausente"),
    ])

    assert "[ERRO ] IA" in report
    assert "[AVISO] Opcional" in report
    assert "requisitos obrigatórios pendentes" in report


def test_report_ready_when_required_checks_pass():
    report = format_report([
        Check("IA", True, True, "ok"),
        Check("Opcional", False, False, "ausente"),
    ])

    assert "Pronto para executar" in report


def test_wakeword_requires_the_actual_model(monkeypatch):
    monkeypatch.setattr("core.readiness._has_module", lambda name: True)
    monkeypatch.setattr(
        "input.stt.ensure_default_wakeword_model",
        lambda download=False: None,
    )
    config = type("Config", (), {"get": lambda self, key, default=None: default})()

    check = _check_wakeword(config, required=True)

    assert check.ok is False
    assert check.required is True
    assert "nao foi baixado" in check.detail


def test_whisper_requires_vad_asset(monkeypatch):
    monkeypatch.setattr("core.readiness._has_module", lambda name: True)
    monkeypatch.setattr("faster_whisper.__file__", "X:/missing/faster_whisper/__init__.py")

    check = _check_whisper(required=True)

    assert check.ok is False
    assert check.required is True
    assert "silero_vad_v6.onnx" in check.detail
