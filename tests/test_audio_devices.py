"""Testes leves para seleção de dispositivos sem hardware real."""

from core.audio_devices import resolve_device_index


class FakePyAudio:
    devices = [
        {"name": "Microfone USB", "maxInputChannels": 1, "maxOutputChannels": 0},
        {"name": "Fone Bluetooth", "maxInputChannels": 0, "maxOutputChannels": 2},
        {"name": "Saída HDMI", "maxInputChannels": 0, "maxOutputChannels": 2},
    ]

    def get_device_count(self):
        return len(self.devices)

    def get_device_info_by_index(self, index):
        return self.devices[index]


def test_resolve_input_by_partial_name():
    assert resolve_device_index(FakePyAudio(), "usb", "input") == 0


def test_resolve_output_by_exact_name():
    assert resolve_device_index(FakePyAudio(), "Fone Bluetooth", "output") == 1


def test_resolve_numeric_string():
    assert resolve_device_index(FakePyAudio(), "2", "output") == 2


def test_empty_or_invalid_uses_system_default():
    pa = FakePyAudio()
    assert resolve_device_index(pa, "", "input") is None
    assert resolve_device_index(pa, "inexistente", "output") is None
