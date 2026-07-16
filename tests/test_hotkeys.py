"""Testes dos atalhos globais sem depender do teclado real."""

import sys
import threading
from types import SimpleNamespace

from input.hotkeys import DEFAULT_HOTKEYS, HotkeyManager
from input.stt import VoiceInput


class _Config:
    pass


def test_start_registers_all_hotkeys(monkeypatch):
    registered = {}
    fake_keyboard = SimpleNamespace(
        add_hotkey=lambda hotkey, callback, suppress=False: registered.setdefault(hotkey, callback),
        wait=lambda: None,
        unhook_all=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "keyboard", fake_keyboard)

    manager = HotkeyManager(_Config(), lambda command: command)

    assert manager.start() is True
    assert set(registered) == set(DEFAULT_HOTKEYS)
    assert manager._active is True


def test_push_to_talk_wakes_voice_loop(monkeypatch):
    requested = []
    voice = SimpleNamespace(request_push_to_talk=lambda: requested.append(True))
    monkeypatch.setattr("input.stt.get_instance", lambda: voice)
    manager = HotkeyManager(_Config(), lambda command: command)

    manager._push_to_talk()

    assert requested == [True]


def test_transcription_hotkey_uses_normal_dispatcher():
    commands = []
    manager = HotkeyManager(_Config(), lambda command: commands.append(command) or "ok")

    manager._call_transcription("start_transcription")
    manager._call_transcription("stop_transcription")

    assert commands == ["começa a transcrever", "para a transcrição"]


def test_voice_input_waits_for_registered_push_to_talk():
    voice = VoiceInput.__new__(VoiceInput)
    voice._push_to_talk_event = threading.Event()
    voice._push_to_talk_hotkey_enabled = True
    voice._capture_and_transcribe = lambda: "comando transcrito"
    voice.request_push_to_talk()

    assert voice._listen_push_to_talk() == "comando transcrito"
