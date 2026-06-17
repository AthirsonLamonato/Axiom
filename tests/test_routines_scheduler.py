"""Testes para o agendador automático de rotinas (modules/routines.py)."""

from datetime import datetime

from modules import routines


def test_matches_schedule_requires_exact_time():
    now = datetime(2026, 6, 16, 8, 0)
    assert routines._matches_schedule({"time": "08:00"}, now) is True
    assert routines._matches_schedule({"time": "08:01"}, now) is False


def test_matches_schedule_respects_days_condition():
    monday = datetime(2026, 6, 15, 9, 0)   # segunda-feira
    saturday = datetime(2026, 6, 20, 9, 0)  # sábado
    schedule = {"time": "09:00", "days": "weekday"}
    assert routines._matches_schedule(schedule, monday) is True
    assert routines._matches_schedule(schedule, saturday) is False


def test_matches_schedule_daily_ignores_days():
    now = datetime(2026, 6, 20, 7, 30)
    assert routines._matches_schedule({"time": "07:30", "days": "daily"}, now) is True


def test_scheduler_loop_runs_routine_once_per_day(monkeypatch):
    routines._last_run_date.clear()
    fake_config = {"routines": {"teste": {"schedule": {"time": "10:00", "days": "daily"}}}}
    monkeypatch.setattr(routines, "_get_config", lambda: type(
        "C", (), {"get": lambda self, k, d=None: fake_config.get(k, d)}
    )())

    called = []
    monkeypatch.setattr(routines, "run", lambda name: called.append(name))

    fixed_now = datetime(2026, 6, 16, 10, 0)
    monkeypatch.setattr(routines, "datetime", type("D", (), {"now": staticmethod(lambda: fixed_now)}))

    routines._scheduler_running = True

    def fake_sleep(_):
        routines._scheduler_running = False

    monkeypatch.setattr(routines.time, "sleep", fake_sleep)
    routines._scheduler_loop()

    assert called == ["teste"]
