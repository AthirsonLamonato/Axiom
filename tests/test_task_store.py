from unittest.mock import patch

import pytest

from modules import task_store


def setup_function():
    task_store._TASKS.clear()


def test_create_and_list_plan():
    task = task_store.create([
        {"tool": "browser_inspect", "args": {}, "description": "Ler página"}
    ])
    assert task["status"] == "pending"
    assert task_store.list_tasks()[0]["id"] == task["id"]


def test_reject_pending_plan():
    task = task_store.create([{"tool": "browser_close", "args": {}}])
    rejected = task_store.reject(task["id"])
    assert rejected["status"] == "rejected"


def test_approve_runs_and_records_results():
    task = task_store.create([{"tool": "browser_inspect", "args": {}}])
    with patch("modules.intent._execute_tool", return_value="Página lida") as execute, patch(
        "modules.intent._needs_confirmation", return_value=False
    ):
        completed = task_store.approve_and_run(task["id"])
    assert completed["status"] == "completed"
    assert completed["results"][0]["output"] == "Página lida"
    execute.assert_called_once()


def test_sensitive_arguments_are_redacted_in_public_plan():
    task = task_store.create([{"tool": "browser_fill", "args": {"selector": "#password", "password": "segredo"}}])
    assert task["steps"][0]["args"]["password"] == "[oculto]"
    stored = task_store._TASKS[task["id"]]
    assert stored["steps"][0]["args"]["password"] == "segredo"


def test_plan_limits_number_of_steps():
    with pytest.raises(ValueError, match="entre 1 e"):
        task_store.create([])
    with pytest.raises(ValueError, match="entre 1 e"):
        task_store.create([{"tool": "browser_inspect", "args": {}}] * 31)



def test_cancel_pending_plan():
    task = task_store.create([{"tool": "browser_inspect", "args": {}}])
    cancelled = task_store.cancel(task["id"])
    assert cancelled["status"] == "cancelled"
    assert "antes da execução" in cancelled["error"]


def test_cancel_running_plan_sets_request_event():
    task = task_store.create([{"tool": "browser_inspect", "args": {}}])
    with task_store._LOCK:
        task_store._TASKS[task["id"]]["status"] = "running"
        import threading
        task_store._CANCEL_EVENTS[task["id"]] = threading.Event()
    cancelled = task_store.cancel(task["id"])
    assert cancelled["status"] == "running"
    assert cancelled["cancel_requested"] is True
    assert task_store._CANCEL_EVENTS[task["id"]].is_set()
    task_store._CANCEL_EVENTS.pop(task["id"], None)
