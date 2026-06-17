"""Testes para o agendador proativo de insights de aprendizado (modules/learner.py)."""

from modules import learner


def _config_with(proactive=True, interval_hours=24):
    return type("C", (), {
        "get": lambda self, k, d=None: {
            "learner.proactive_enabled": proactive,
            "learner.interval_hours": interval_hours,
        }.get(k, d)
    })()


def test_fire_insight_skips_when_no_interactions(monkeypatch):
    monkeypatch.setattr(learner, "analyze_and_optimize", lambda: "Nenhuma interação registrada ainda.")
    saved = []
    monkeypatch.setattr("storage.file_store.save_text", lambda text, prefix, ext: saved.append(text))

    learner._fire_insight()

    assert saved == []


def test_fire_insight_saves_and_notifies(monkeypatch):
    monkeypatch.setattr(learner, "analyze_and_optimize", lambda: "Taxa de sucesso: 90%")
    monkeypatch.setattr("storage.file_store.save_text", lambda text, prefix, ext: "/tmp/learning_insight_1.md")

    notified = []
    monkeypatch.setattr("output.notifier.notify", lambda title, msg: notified.append(msg))

    learner._fire_insight()

    assert notified  # disparou notificação proativa


def test_scheduler_loop_fires_once_interval_elapsed(monkeypatch):
    monkeypatch.setattr("core.config.Config", lambda: _config_with(True, 0.0001))
    learner._last_run_ts = 0.0
    learner._scheduler_running = True

    fired = []
    monkeypatch.setattr(learner, "_fire_insight", lambda: fired.append(True))

    def fake_sleep(_):
        learner._scheduler_running = False

    monkeypatch.setattr(learner.time, "sleep", fake_sleep)
    learner._scheduler_loop()

    assert fired == [True]


def test_scheduler_loop_respects_disabled_flag(monkeypatch):
    monkeypatch.setattr("core.config.Config", lambda: _config_with(False, 0.0001))
    learner._last_run_ts = 0.0
    learner._scheduler_running = True

    fired = []
    monkeypatch.setattr(learner, "_fire_insight", lambda: fired.append(True))

    def fake_sleep(_):
        learner._scheduler_running = False

    monkeypatch.setattr(learner.time, "sleep", fake_sleep)
    learner._scheduler_loop()

    assert fired == []
