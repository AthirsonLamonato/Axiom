"""Testes para input/stt.py — sem microfone real."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Todos os testes neste arquivo requerem recursos externos pesados
# (Whisper model download, PyAudio). Marcados como integration para
# não travar o CI padrão.
pytestmark = pytest.mark.integration


@pytest.fixture
def config(tmp_path):
    import yaml
    from core.config import Config
    data = {
        "wake_word": {"enabled": False, "sensitivity": 0.5, "model_path": ""},
        "stt": {"model": "base", "language": "pt", "device": "cpu", "auto_calibrate": False},
        "logging": {"level": "WARNING", "file": "logs/pacoca.log", "max_mb": 10},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return Config(str(path))


@pytest.fixture
def voice_input(config):
    """Instancia VoiceInput e fecha ao fim do teste."""
    from input.stt import VoiceInput
    v = VoiceInput(config)
    yield v
    v.close()


def test_voice_input_init_push_to_talk(voice_input):
    """Com wake_word.enabled=False deve iniciar em modo push-to-talk."""
    assert voice_input._mode == "push_to_talk"
    assert voice_input._oww is None
    assert voice_input._whisper is not None


def test_voice_input_whisper_transcribes_audio(voice_input):
    """Whisper deve transcrever áudio sintético sem erros."""
    import numpy as np
    from input.stt import SAMPLE_RATE, MAX_COMMAND_DURATION

    silence = np.zeros(int(SAMPLE_RATE * MAX_COMMAND_DURATION), dtype=np.float32)
    segments, _ = voice_input._whisper.transcribe(silence, language="pt", vad_filter=True)
    result = " ".join(s.text for s in segments).strip()
    assert isinstance(result, str)


def test_transcribe_file_returns_string(voice_input, tmp_path):
    """transcribe_file deve retornar str mesmo para arquivo de silêncio."""
    import wave
    import struct
    from input.stt import SAMPLE_RATE

    wav_path = str(tmp_path / "silence.wav")
    samples = [0] * (SAMPLE_RATE * 2)
    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"{len(samples)}h", *samples))

    result = voice_input.transcribe_file(wav_path)
    assert isinstance(result, str)
