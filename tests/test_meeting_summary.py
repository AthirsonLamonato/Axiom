"""Testes para o resumo automático pós-reunião (modules/meeting_detector.py)."""

from modules import meeting_detector


def test_auto_summarize_saves_and_notifies(monkeypatch):
    monkeypatch.setattr("modules.summarizer.summarize_meeting", lambda: "## Resumo\nDecisão X tomada.")
    monkeypatch.setattr("storage.file_store.save_text", lambda text, prefix, ext: "/tmp/meeting_summary_1.md")

    notified = []
    monkeypatch.setattr("output.notifier.notify", lambda title, msg: notified.append(msg))

    meeting_detector._auto_summarize()

    assert notified and "meeting_summary_1.md" in notified[0]


def test_auto_summarize_skips_when_no_transcription(monkeypatch):
    monkeypatch.setattr("modules.summarizer.summarize_meeting", lambda: "Nenhuma transcrição disponível.")
    saved = []
    monkeypatch.setattr("storage.file_store.save_text", lambda text, prefix, ext: saved.append(text))

    meeting_detector._auto_summarize()

    assert saved == []


def test_on_meeting_end_triggers_auto_summarize_when_enabled(monkeypatch):
    monkeypatch.setattr("modules.transcription.stop", lambda: "ok")
    monkeypatch.setattr("core.profiles._get_manager", lambda: type(
        "M", (), {"switch": lambda self, p: None}
    )())
    monkeypatch.setattr("output.notifier.notify", lambda *a, **k: None)

    fired = []
    monkeypatch.setattr(meeting_detector.threading, "Thread", lambda target, daemon: type(
        "T", (), {"start": lambda self: fired.append(target)}
    )())
    monkeypatch.setattr("core.config.Config", lambda: type(
        "C", (), {"get": lambda self, k, d=None: True}
    )())

    meeting_detector._on_meeting_end()

    assert fired == [meeting_detector._auto_summarize]
