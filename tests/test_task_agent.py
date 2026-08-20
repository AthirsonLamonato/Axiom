from unittest.mock import patch

from modules.task_agent import TaskStep, execute_steps, plan_from_tool_calls


def test_plan_from_tool_calls_accepts_agentic_shape():
    steps = plan_from_tool_calls([
        {"name": "browser_start", "args": {"url": "about:blank"}},
        {"function": {"name": "browser_inspect", "arguments": {}}},
    ])
    assert [step.tool for step in steps] == ["browser_start", "browser_inspect"]


def test_execute_steps_runs_in_order_and_verifies():
    calls = []

    def fake_execute(name, args):
        calls.append(name)
        return f"ok {name}"

    with patch("modules.intent._execute_tool", side_effect=fake_execute), patch(
        "modules.intent._needs_confirmation", return_value=False
    ):
        result = execute_steps([
            TaskStep("browser_start", {}, verify_contains="ok"),
            TaskStep("browser_inspect", {}, verify_contains="ok"),
        ])

    assert result.ok is True
    assert calls == ["browser_start", "browser_inspect"]
    assert all(item.verified for item in result.results)


def test_execute_steps_stops_when_verification_fails():
    calls = []

    def fake_execute(name, args):
        calls.append(name)
        return "resultado inesperado"

    with patch("modules.intent._execute_tool", side_effect=fake_execute), patch(
        "modules.intent._needs_confirmation", return_value=False
    ):
        result = execute_steps([
            TaskStep("browser_click", {}, verify_contains="clique executado"),
            TaskStep("browser_inspect", {}),
        ])

    assert result.ok is False
    assert calls == ["browser_click"]


def test_execute_steps_requires_confirmation_for_sensitive_action():
    with patch("modules.intent._execute_tool") as execute, patch(
        "modules.intent._needs_confirmation", return_value=True
    ):
        result = execute_steps([TaskStep("browser_fill", {"selector": "#x", "value": "a"})])

    assert result.ok is False
    execute.assert_not_called()
    assert "não executada" in result.output



def test_execute_steps_can_be_cancelled_before_next_step():
    import threading

    calls = []
    cancel = threading.Event()

    def fake_execute(name, args):
        calls.append(name)
        cancel.set()
        return f"ok {name}"

    with patch("modules.intent._execute_tool", side_effect=fake_execute), patch(
        "modules.intent._needs_confirmation", return_value=False
    ):
        result = execute_steps(
            [TaskStep("browser_start", {}), TaskStep("browser_inspect", {})],
            cancel_event=cancel,
        )

    assert result.ok is False
    assert result.cancelled is True
    assert "cancelamento" in result.cancel_reason
    assert calls == ["browser_start"]


def test_execute_steps_stops_after_timeout():
    calls = []

    def fake_execute(name, args):
        calls.append(name)
        return f"ok {name}"

    with patch("modules.intent._execute_tool", side_effect=fake_execute), patch(
        "modules.intent._needs_confirmation", return_value=False
    ):
        result = execute_steps(
            [TaskStep("browser_start", {}), TaskStep("browser_inspect", {})],
            timeout_seconds=0,
        )

    assert result.ok is False
    assert result.cancelled is True
    assert "timeout" in result.cancel_reason
    assert calls == []
