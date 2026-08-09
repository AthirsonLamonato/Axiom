import base64

from modules import system_control


def test_wsl_launcher_quotes_user_value(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(system_control, "OS", "Linux")
    monkeypatch.setattr(system_control.subprocess, "run", fake_run)

    assert system_control._run_win("x'; calc; '") is True
    encoded = captured["args"][-1]
    script = base64.b64decode(encoded).decode("utf-16-le")
    assert script == "Start-Process -FilePath 'x''; calc; '''"
    assert "-EncodedCommand" in captured["args"]


def test_wsl_vscode_launch_does_not_use_shell(monkeypatch):
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(system_control, "IS_WSL", True)
    monkeypatch.setattr(system_control.subprocess, "Popen", fake_popen)

    result = system_control.open_app("VS Code")

    assert result == "Abertura solicitada para VS Code."
    assert captured["args"] == ["code", "."]
    assert "shell" not in captured["kwargs"]
