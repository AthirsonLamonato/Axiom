"""Fila em memória para planos supervisionados do dashboard local."""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from modules.task_agent import TaskStep, execute_steps

_LOCK = threading.RLock()
_TASKS: dict[str, dict[str, Any]] = {}
_MAX_STEPS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(steps: list[dict[str, Any]]) -> dict[str, Any]:
    if not steps or len(steps) > _MAX_STEPS:
        raise ValueError(f"O plano precisa ter entre 1 e {_MAX_STEPS} etapas.")
    normalized = []
    for item in steps:
        if not isinstance(item, dict) or not isinstance(item.get("tool"), str) or not isinstance(item.get("args", {}), dict):
            raise ValueError("Cada etapa precisa ter 'tool' e um objeto 'args'.")
        normalized.append({
            "tool": item["tool"],
            "args": item.get("args", {}),
            "description": item.get("description", ""),
            "verify_contains": item.get("verify_contains", ""),
        })
    task_id = uuid.uuid4().hex[:12]
    task = {
        "id": task_id,
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now(),
        "steps": normalized,
        "results": [],
        "error": None,
    }
    with _LOCK:
        _TASKS[task_id] = task
    return task.copy()


def get(task_id: str) -> dict[str, Any] | None:
    with _LOCK:
        task = _TASKS.get(task_id)
        return task.copy() if task else None


def list_tasks(limit: int = 20) -> list[dict[str, Any]]:
    with _LOCK:
        items = list(_TASKS.values())[-max(1, min(limit, 100)):]
        return [item.copy() for item in reversed(items)]


def approve_and_run(task_id: str, confirm=None) -> dict[str, Any]:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise KeyError("Tarefa não encontrada.")
        if task["status"] != "pending":
            raise ValueError(f"Tarefa não está pendente: {task['status']}.")
        task["status"] = "running"
        task["updated_at"] = _now()
    try:
        steps = [TaskStep(**item) for item in task["steps"]]
        result = execute_steps(steps, confirm=confirm)
        with _LOCK:
            task["status"] = "completed" if result.ok else "failed"
            task["results"] = [
                {"tool": item.step.tool, "ok": item.ok, "verified": item.verified, "output": item.output}
                for item in result.results
            ]
            task["updated_at"] = _now()
        return task.copy()
    except Exception as exc:
        with _LOCK:
            task["status"] = "failed"
            task["error"] = str(exc)
            task["updated_at"] = _now()
        return task.copy()


def reject(task_id: str) -> dict[str, Any]:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise KeyError("Tarefa não encontrada.")
        if task["status"] != "pending":
            raise ValueError(f"Tarefa não está pendente: {task['status']}.")
        task["status"] = "rejected"
        task["updated_at"] = _now()
        return task.copy()
