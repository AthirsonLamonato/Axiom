"""Servidor MCP local do Paçoca.

Expõe somente ferramentas de baixo risco. Ações destrutivas ou externas ficam
fora do servidor até existir confirmação remota autenticada.
"""

from typing import Literal

from mcp.server import MCPServer

from modules.tools import execute, validate


mcp = MCPServer(
    "Paçoca Desktop",
    version="0.9.0",
    instructions=(
        "Ferramentas locais para controlar o computador do usuário. "
        "Confirme o resultado retornado; nunca presuma que uma ação funcionou."
    ),
)


def _run(name: str, arguments: dict) -> str:
    validated, error = validate(name, arguments)
    if validated is None:
        raise ValueError(error)
    result = execute(name, validated)
    if result.startswith("Erro"):
        raise RuntimeError(result)
    return result


@mcp.tool()
def current_time() -> str:
    """Retorna horário local atual do computador."""
    from modules.local_info import current_time as get_current_time

    return get_current_time()


@mcp.tool()
def current_date() -> str:
    """Retorna data local atual do computador."""
    from modules.local_info import current_date as get_current_date

    return get_current_date()


@mcp.tool()
def open_application(name: str) -> str:
    """Abre aplicativo instalado pelo nome."""
    return _run("open_application", {"name": name})


@mcp.tool()
def open_browser(
    destination: str,
    browser: Literal["chrome", "firefox", "brave", "edge"] = "brave",
) -> str:
    """Abre navegador em site ou pesquisa informada."""
    return _run("open_browser", {"browser": browser, "destination": destination})


@mcp.tool()
def open_folder(path: str) -> str:
    """Abre pasta local existente ou pasta conhecida pelo nome."""
    return _run("open_folder", {"path": path})


@mcp.tool()
def set_volume(level: int) -> str:
    """Define volume principal entre 0 e 100."""
    return _run("set_volume", {"level": level})


@mcp.tool()
def control_media(
    action: Literal["play", "pause", "resume", "next", "previous", "current"],
    query: str | None = None,
) -> str:
    """Controla mídia; query é obrigatória quando action for play."""
    return _run("control_media", {"action": action, "query": query})


@mcp.tool()
def web_search(query: str) -> str:
    """Pesquisa web gratuitamente e retorna síntese do resultado."""
    return _run("web_search", {"query": query})


@mcp.tool()
def list_memories(filter: str = "") -> str:
    """Lista memórias locais; filtro opcional: preferences, habits, projects ou facts."""
    return _run("list_memories", {"filter": filter})


if __name__ == "__main__":
    mcp.run()
