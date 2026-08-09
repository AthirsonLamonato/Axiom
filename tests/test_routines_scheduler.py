"""Testes para o agendador automático de rotinas (modules/routines.py)."""

from datetime import date, datetime

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


def test_unknown_condition_is_fail_closed():
    assert routines._evaluate_condition("typo", datetime(2026, 6, 20, 7, 30)) is False


def test_build_step_validates_action_and_value():
    assert routines.build_step("notify", "olá") == {"action": "notify", "message": "olá"}
    assert routines.build_step("set_volume", "42") == {"action": "set_volume", "target": "42"}

    import pytest
    with pytest.raises(ValueError):
        routines.build_step("shell", "echo x")
    with pytest.raises(ValueError):
        routines.build_step("set_volume", "101")


def test_scheduler_loop_runs_routine_once_per_day(monkeypatch, tmp_path):
    routines._last_run_date.clear()
    routines._schedule_state_loaded = False
    monkeypatch.setattr(routines, "SCHEDULE_STATE_PATH", tmp_path / "routine_schedule.json")
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
    assert routines.SCHEDULE_STATE_PATH.exists()


def test_schedule_state_survives_restart(monkeypatch, tmp_path):
    state_path = tmp_path / "routine_schedule.json"
    monkeypatch.setattr(routines, "SCHEDULE_STATE_PATH", state_path)
    routines._last_run_date.clear()
    routines._last_run_date["teste"] = date(2026, 6, 16)
    routines._save_schedule_state()

    routines._last_run_date.clear()
    routines._schedule_state_loaded = False
    routines._load_schedule_state()

    assert routines._last_run_date == {"teste": date(2026, 6, 16)}
