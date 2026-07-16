"""Regressões do adaptador de notificações de desktop."""

from output import notifier


def test_windows_balloon_failure_is_swallowed(monkeypatch):
    def failing_balloon(**_kwargs):
        raise RuntimeError("Shell_NotifyIconW failed")

    monkeypatch.setattr(notifier, "_load_windows_balloon", lambda: failing_balloon)

    notifier._notify_windows("Paçoca", "Teste")


def test_windows_notification_uses_guarded_daemon_thread(monkeypatch):
    started = {}

    class ImmediateThread:
        def __init__(self, *, target, args, daemon, name):
            started.update(target=target, args=args, daemon=daemon, name=name)

        def start(self):
            started["target"](*started["args"])

    monkeypatch.setattr(notifier.platform, "system", lambda: "Windows")
    monkeypatch.setattr(notifier.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(notifier, "_notify_windows", lambda title, message: None)

    notifier.notify("Paçoca", "Teste")

    assert started["daemon"] is True
    assert started["name"] == "pacoca-notification"
