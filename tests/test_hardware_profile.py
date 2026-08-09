from core import hardware_profile


def test_detect_returns_actionable_profile(monkeypatch):
    monkeypatch.setattr(hardware_profile, "_detect_vram_gb", lambda: 0.0)
    profile = hardware_profile.detect()
    assert profile.name in {"leve", "equilibrado", "completo", "potente"}
    assert profile.ollama_model
    assert profile.whisper_model
    assert profile.cpu_threads >= 1
