import argparse


def test_doctor_applies_runtime_flags_before_checks(monkeypatch):
    import main

    seen = {}

    class FakeConfig:
        def __init__(self):
            self.values = {}

        def set(self, key, value):
            self.values[key] = value

    config = FakeConfig()
    monkeypatch.setattr(main, "Config", lambda: config)
    monkeypatch.setattr(main, "_ensure_directories", lambda: None)
    monkeypatch.setattr(main, "setup_logging", lambda _config: None)
    monkeypatch.setattr(main.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(
            mode="text",
            profile="casual",
            no_tts=True,
            no_overlay=True,
            edit_routines=False,
            web=False,
            doctor=True,
            hands_free=False,
            no_hands_free=False,
            install_startup=False,
            remove_startup=False,
        ),
    )

    def fake_doctor(received_config, mode, web):
        seen.update(config=received_config, mode=mode, web=web)
        return True, "ok"

    monkeypatch.setattr("core.readiness.doctor", fake_doctor)
    assert main.main() == 0
    assert seen["config"] is config
    assert seen["mode"] == "text"
    assert seen["web"] is False
    assert config.values == {
        "tts.enabled": False,
        "overlay.enabled": False,
        "profile.active": "casual",
    }


def test_doctor_returns_failure_status(monkeypatch):
    import main

    class FakeConfig:
        def set(self, *_args):
            pass

    monkeypatch.setattr(main, "Config", FakeConfig)
    monkeypatch.setattr(main, "_ensure_directories", lambda: None)
    monkeypatch.setattr(main, "setup_logging", lambda _config: None)
    monkeypatch.setattr(main.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(
            mode="text",
            profile=None,
            no_tts=False,
            no_overlay=False,
            edit_routines=False,
            web=False,
            doctor=True,
            hands_free=False,
            no_hands_free=False,
            install_startup=False,
            remove_startup=False,
        ),
    )
    monkeypatch.setattr("core.readiness.doctor", lambda *_args, **_kwargs: (False, "erro"))
    assert main.main() == 1


def test_parse_args_supports_hands_free_flags(monkeypatch):
    import main

    monkeypatch.setattr("sys.argv", ["main.py", "--hands-free"])
    args = main.parse_args()

    assert args.hands_free is True
    assert args.no_hands_free is False


def test_parse_args_supports_startup_flags(monkeypatch):
    import main

    monkeypatch.setattr("sys.argv", ["main.py", "--remove-startup"])
    args = main.parse_args()

    assert args.remove_startup is True
    assert args.install_startup is False
