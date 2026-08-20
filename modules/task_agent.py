"""Planejamento e execução supervisionada de tarefas compostas.

O módulo não inventa permissões próprias: reutiliza o ToolRegistry e o callback
de confirmação do orquestrador. Cada etapa é validada, executada e verificada
antes da próxima etapa começar.
"""

from __future__ import annotations

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

    @property
    def output(self) -> str:
        return "\n".join(r.output for r in self.results)


def _execute_with_confirmation(tool: str, args: dict, confirm: Callable[[str, dict], bool] | None) -> str:
    from modules.intent import _execute_tool, _needs_confirmation

    if _needs_confirmation(tool, args):
        if confirm is None or not confirm(tool, args):
            return f"Ação '{tool}' não executada: confirmação negada ou indisponível."
    return _execute_tool(tool, args)


def execute_steps(
    steps: Iterable[TaskStep],
    confirm: Callable[[str, dict], bool] | None = None,
) -> TaskResult:
    """Executa etapas em ordem e para no primeiro erro ou falha de verificação."""
    result = TaskResult(ok=True)
    for step in steps:
        output = _execute_with_confirmation(step.tool, step.args, confirm)
        lowered = output.lower()
        failed = lowered.startswith(("erro", "args inválidos", "ferramenta desconhecida")) or "não executada" in lowered
        verified = not step.verify_contains or step.verify_contains.lower() in lowered
        item = StepResult(step=step, ok=not failed and verified, output=output, verified=verified)
        result.results.append(item)
        if not item.ok:
            result.ok = False
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
