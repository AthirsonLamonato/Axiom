"""Executor supervisionado de planos de tarefas.

Cada etapa é validada, confirmada, executada e verificada antes da próxima.
O executor também oferece cancelamento cooperativo e timeout total para evitar
que uma automação fique presa indefinidamente.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass(frozen=True)
class TaskStep:
    tool: str
    args: dict
    description: str = ""
    verify_contains: str = ""


@dataclass
class StepResult:
    step: TaskStep
    ok: bool
    output: str
    verified: bool = False


@dataclass
class TaskResult:
    ok: bool
    results: list[StepResult] = field(default_factory=list)
    cancelled: bool = False
    cancel_reason: str = ""

    @property
    def output(self) -> str:
        return "\n".join(r.output for r in self.results)


def _execute_with_confirmation(
    tool: str,
    args: dict,
    confirm: Callable[[str, dict], bool] | None,
) -> str:
    from modules.intent import _execute_tool, _needs_confirmation

    if _needs_confirmation(tool, args):
        if confirm is None or not confirm(tool, args):
            return f"Ação '{tool}' não executada: confirmação negada ou indisponível."
    return _execute_tool(tool, args)


def execute_steps(
    steps: Iterable[TaskStep],
    confirm: Callable[[str, dict], bool] | None = None,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float | None = None,
) -> TaskResult:
    """Executa etapas em ordem e para no primeiro erro ou falha de verificação.

    ``cancel_event`` permite interromper o plano entre etapas. O timeout é total
    para o plano e não tenta matar uma ferramenta já executando; nesse caso a
    ferramenta termina naturalmente e nenhuma etapa posterior é iniciada.
    """
    result = TaskResult(ok=True)
    started = time.monotonic()
    timeout = max(0.0, float(timeout_seconds)) if timeout_seconds is not None else None
    event = cancel_event or threading.Event()

    def stop_reason() -> str:
        if event.is_set():
            return "cancelamento solicitado pelo usuário"
        if timeout is not None and time.monotonic() - started >= timeout:
            return f"timeout do plano ({timeout:g}s)"
        return ""

    for step in steps:
        reason = stop_reason()
        if reason:
            result.ok = False
            result.cancelled = True
            result.cancel_reason = reason
            result.results.append(
                StepResult(step=step, ok=False, output=f"Plano interrompido: {reason}.")
            )
            break

        output = _execute_with_confirmation(step.tool, step.args, confirm)
        lowered = output.lower()
        failed = lowered.startswith(("erro", "args inválidos", "ferramenta desconhecida")) or "não executada" in lowered
        verified = not step.verify_contains or step.verify_contains.lower() in lowered
        item = StepResult(step=step, ok=not failed and verified, output=output, verified=verified)
        result.results.append(item)
        if not item.ok:
            result.ok = False
            break

        reason = stop_reason()
        if reason:
            result.ok = False
            result.cancelled = True
            result.cancel_reason = reason
            break

    return result


def plan_from_tool_calls(tool_calls: Iterable[dict]) -> list[TaskStep]:
    """Converte chamadas no formato do loop agentivo em etapas auditáveis."""
    steps = []
    for call in tool_calls:
        name = call.get("name") or call.get("function", {}).get("name")
        args = call.get("args") or call.get("arguments") or call.get("function", {}).get("arguments") or {}
        if isinstance(args, str):
            import json
            args = json.loads(args)
        if not name or not isinstance(args, dict):
            raise ValueError("Chamada de ferramenta inválida para criação do plano.")
        steps.append(TaskStep(tool=name, args=args, description=f"Executar {name}"))
    return steps
