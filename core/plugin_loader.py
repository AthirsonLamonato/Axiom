"""
core/plugin_loader.py — Carregador dinâmico de plugins externos
Escaneia plugins/ na inicialização e injeta as rotas no Orchestrator.
Plugins podem ser recarregados em tempo real via comando de voz.
"""

import importlib
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# name → {module, version, description, routes}
_registry: dict = {}
_orchestrator: "Orchestrator | None" = None


def set_orchestrator(orc: "Orchestrator") -> None:
    global _orchestrator
    _orchestrator = orc


def load_all(plugins_dir: str = "plugins") -> list:
    """Importa todos os plugins do diretório e retorna a lista combinada de rotas."""
    global _registry
    _registry = {}

    if not os.path.isdir(plugins_dir):
        logger.debug("Diretório '%s' não encontrado — nenhum plugin carregado.", plugins_dir)
        return []

    routes = []
    for fname in sorted(os.listdir(plugins_dir)):
        if fname.startswith("_") or not fname.endswith(".py"):
            continue
        module_name = f"plugins.{fname[:-3]}"
        try:
            # Recarrega se já estava importado (suporte a reload)
            if module_name in importlib.import_module("sys").modules:
                mod = importlib.reload(importlib.import_module(module_name))
            else:
                mod = importlib.import_module(module_name)

            plugin_routes = getattr(mod, "ROUTES", [])
            name        = getattr(mod, "NAME",        fname[:-3])
            version     = getattr(mod, "VERSION",     "1.0")
            description = getattr(mod, "DESCRIPTION", "")

            _registry[name] = {
                "module":      module_name,
                "version":     version,
                "description": description,
                "routes":      len(plugin_routes),
            }
            routes.extend(plugin_routes)
            logger.info("Plugin: %s v%s carregado (%d rota(s))", name, version, len(plugin_routes))

        except Exception as e:
            logger.warning("Falha ao carregar plugin '%s': %s", fname, e, exc_info=True)

    return routes


# ── Comandos de voz ────────────────────────────────────────────────────

def list_loaded(*_) -> str:
    if not _registry:
        return "Nenhum plugin carregado."
    lines = ["Plugins ativos:"]
    for name, info in _registry.items():
        lines.append(
            f"  • {name} v{info['version']} — {info['description']} "
            f"({info['routes']} rota(s))"
        )
    return "\n".join(lines)


def reload_all(*_) -> str:
    if _orchestrator is None:
        return "Orchestrator não inicializado."
    _orchestrator._reload_plugins()
    n = len(_registry)
    return f"Plugins recarregados. {n} plugin(s) ativo(s)."
