"""Fila persistente de planos supervisionados do dashboard local."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.task_agent import TaskStep, execute_steps

_LOCK = threading.RLock()
_MAX_STEPS = 30
_DEFAULT_PATH = Path("data") / "task-plans.json"
_STORE_PATH = Path(os.environ.get("PACOCA_TASK_STORE", str(_DEFAULT_PATH)))
_TASKS: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_locked() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = _STORE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(_TASKS, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(_STORE_PATH)


def _load() -> None:
    if not _STORE_PATH.exists():
        return
    try:
        loaded = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            for task_id, task in loaded.items():
                if isinstance(task, dict) and isinstance(task_id, str):
                    if task.get("status") == "running":
                        task["status"] = "failed"
                        task["error"] = "Execução interrompida quando o Paçoca foi reiniciado."
                        task["updated_at"] = _now()
                    _TASKS[task_id] = task
    except (OSError, ValueError):
        # Um arquivo corrompido não impede o dashboard de iniciar.
        return


def _redact(value: Any, key: str = "") -> Any:
    sensitive = ("password", "passwd", "secret", "token", "api_key", "apikey", "cookie", "authorization")
    if any(part in key.lower() for part in sensitive):
        return "[oculto]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, key) for v in value]
    return value


def _public(task: dict[str, Any]) -> dict[str, Any]:
    return _redact(task)


_load()


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
        _persist_locked()
    return _public(task)


def get(task_id: str) -> dict[str, Any] | None:
    with _LOCK:
        task = _TASKS.get(task_id)
        return _public(task) if task else None


def list_tasks(limit: int = 20) -> list[dict[str, Any]]:
    with _LOCK:
        items = list(_TASKS.values())[-max(1, min(limit, 100)):]
        return [_public(item) for item in reversed(items)]


def approve_and_run(task_id: str, confirm=None) -> dict[str, Any]:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise KeyError("Tarefa não encontrada.")
        if task["status"] != "pending":
            raise ValueError(f"Tarefa não está pendente: {task['status']}.")
        task["status"] = "running"
        task["updated_at"] = _now()
        _persist_locked()
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
            _persist_locked()
        return _public(task)
    except Exception as exc:
        with _LOCK:
            task["status"] = "failed"
            task["error"] = str(exc)
            task["updated_at"] = _now()
            _persist_locked()
        return _public(task)


def reject(task_id: str) -> dict[str, Any]:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            raise KeyError("Tarefa não encontrada.")
        if task["status"] != "pending":
            raise ValueError(f"Tarefa não está pendente: {task['status']}.")
        task["status"] = "rejected"
        task["updated_at"] = _now()
        _persist_locked()
        return _public(task)
