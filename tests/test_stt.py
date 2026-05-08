"""Testes para input/stt.py — sem microfone real."""

import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def config(tmp_path):
    import yaml
    from core.config import Config
    data = {
        "wake_word": {"keyword": "porcupine", "sensitivity": 0.5, "access_key": ""},
        "stt": {"model": "base", "language": "pt", "device": "cpu", "auto_calibrate": False},
        "logging": {"level": "WARNING", "file": "logs/axiom.log", "max_mb": 10},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return Config(str(path))


def test_voice_input_init_push_to_talk(config):
    """Sem access_key deve iniciar em modo push-to-talk."""
    from input.stt import VoiceInput
    v = VoiceInput(config)
    assert v._mode == "push_to_talk"
    assert v._porcupine is None
    assert v._whisper is not None
    assert v._pa is not None
    v.close()


def test_voice_input_whisper_transcribes_audio(config):
    """Whisper deve transcrever áudio sintético sem erros (resultado pode ser vazio)."""
    from input.stt import VoiceInput, SAMPLE_RATE, MAX_COMMAND_DURATION
    v = VoiceInput(config)

    # áudio de silêncio: resultado esperado é string vazia ou curta
    silence = np.zeros(int(SAMPLE_RATE * MAX_COMMAND_DURATION), dtype=np.float32)
    segments, _ = v._whisper.transcribe(silence, language="pt", vad_filter=True)
    result = " ".join(s.text for s in segments).strip()

    assert isinstance(result, str)
    v.close()


def test_transcribe_file_returns_string(config, tmp_path):
    """transcribe_file deve retornar str mesmo para arquivo de silêncio."""
    import wave, struct
    from input.stt import VoiceInput, SAMPLE_RATE

    wav_path = str(tmp_path / "silence.wav")
    samples = [0] * (SAMPLE_RATE * 2)
    with wave.open(wav_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"{len(samples)}h", *samples))

    v = VoiceInput(config)
    result = v.transcribe_file(wav_path)
    assert isinstance(result, str)
    v.close()
