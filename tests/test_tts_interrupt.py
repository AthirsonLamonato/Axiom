"""Testes da interrupção de fala usada pelo barge-in da wake word."""

import threading

from output.tts import TTS


class _FakeProcess:
    def __init__(self):
        self.terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True


def test_stop_interrupts_current_player():
    tts = TTS.__new__(TTS)
    tts._stop_event = threading.Event()
    tts._playback_lock = threading.Lock()
    tts._playback_process = _FakeProcess()
    tts._engine = None

    tts.stop()

    assert tts._stop_event.is_set()
    assert tts._playback_process.terminated is True
