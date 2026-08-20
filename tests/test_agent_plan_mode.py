from unittest.mock import patch

from modules.intent import _defer_tool_calls_to_dashboard
from modules import task_store


def setup_function():
    task_store._TASKS.clear()


def test_defer_tool_calls_creates_pending_plan_without_execution():
    calls = [{
        "function": {
            "name": "browser_navigate",
            "arguments": '{"url": "https://example.com"}',
        }
    }]
    with patch("modules.intent._execute_tool") as execute:
        response = _defer_tool_calls_to_dashboard(calls, "abra example.com")
    task = task_store.list_tasks()[0]
    assert task["status"] == "pending"
    assert task["steps"][0]["tool"] == "browser_navigate"
    assert "Revise e aprove" in response
    execute.assert_not_called()
