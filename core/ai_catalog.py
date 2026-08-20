"""Catálogo e seleção de modelos locais para o Paçoca.

A seleção é determinística e não faz chamadas externas. Ela serve para o primeiro
boot do agente e pode ser sobrescrita explicitamente em ``core/config.yaml``.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class LocalModel:
    name: str
    role: str
    min_ram_gb: float
    recommended_ram_gb: float
    tools: bool = False
    vision: bool = False
    reasoning: bool = False
    notes: str = ""


CATALOG: tuple[LocalModel, ...] = (
    LocalModel("qwen3:1.7b", "general", 3.0, 4.0, tools=True, notes="Leve para computadores com pouca RAM."),
    LocalModel("qwen3:4b", "general", 5.0, 8.0, tools=True, reasoning=True, notes="Equilíbrio recomendado para o agente."),
    LocalModel("qwen3:8b", "general", 8.0, 12.0, tools=True, reasoning=True),
    LocalModel("qwen2.5:3b", "general", 4.0, 6.0, tools=True),
    LocalModel("llama3.2:3b", "general", 4.0, 6.0, tools=True),
    LocalModel("gemma3:4b", "general", 5.0, 8.0, vision=True),
    LocalModel("qwen2.5-coder:3b", "coding", 4.0, 6.0, tools=True, notes="Auxiliar para código."),
    LocalModel("qwen2.5-coder:7b", "coding", 8.0, 12.0, tools=True),
    LocalModel("deepseek-r1:7b", "reasoning", 8.0, 12.0, reasoning=True, notes="Mais lento; útil para planos complexos."),
)

EMBEDDING_MODELS = ("nomic-embed-text", "mxbai-embed-large", "bge-m3", "qwen3-embedding")


def system_ram_gb() -> Optional[float]:
    """Retorna RAM total em GB sem falhar em ambientes mínimos."""
    try:
        import psutil
        return round(float(psutil.virtual_memory().total) / (1024 ** 3), 1)
    except Exception:
        return None


def list_models(role: Optional[str] = None, tools_only: bool = False) -> list[dict]:
    models = CATALOG
    if role:
        models = tuple(m for m in models if m.role == role or m.role == "general")
    if tools_only:
        models = tuple(m for m in models if m.tools)
    return [asdict(model) for model in models]


def recommend_model(ram_gb: Optional[float] = None, role: str = "general") -> LocalModel:
    """Escolhe o maior modelo adequado sem ultrapassar a RAM recomendada."""
    ram = ram_gb if ram_gb is not None else system_ram_gb()
    candidates = [m for m in CATALOG if m.role == role or m.role == "general"]
    if role == "general":
        candidates = [m for m in candidates if m.tools]
    if ram is None:
        return next(m for m in candidates if m.name == "qwen3:1.7b")
    eligible = [m for m in candidates if m.min_ram_gb <= ram]
    if not eligible:
        return next(m for m in candidates if m.name == "qwen3:1.7b")
    return max(eligible, key=lambda m: m.recommended_ram_gb)


def recommended_config(ram_gb: Optional[float] = None) -> dict:
    model = recommend_model(ram_gb, "general")
    return {
        "provider": "ollama",
        "model": model.name,
        "ram_gb": ram_gb if ram_gb is not None else system_ram_gb(),
        "reason": model.notes or "Modelo local compatível com a memória detectada.",
        "embeddings_provider": "ollama",
        "embeddings_model": "nomic-embed-text",
    }
