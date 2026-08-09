"""Perfil local recomendado conforme RAM, CPU e VRAM detectáveis."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareProfile:
    name: str
    ram_gb: float
    cpu_threads: int
    vram_gb: float
    ollama_model: str
    whisper_model: str


def _detect_vram_gb() -> float:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return max(float(line.strip()) for line in result.stdout.splitlines() if line.strip()) / 1024
    except Exception:
        pass
    return 0.0


def detect() -> HardwareProfile:
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        ram_gb = 0.0
    threads = os.cpu_count() or 1
    vram_gb = _detect_vram_gb()

    if ram_gb and ram_gb < 8:
        name, model, whisper = "leve", "llama3.2:1b", "tiny"
    elif ram_gb < 16 and vram_gb < 6:
        name, model, whisper = "equilibrado", "llama3.2:3b", "base"
    elif ram_gb < 32 and vram_gb < 10:
        name, model, whisper = "completo", "llama3.1:8b", "small"
    else:
        name, model, whisper = "potente", "llama3.1:8b", "medium"
    return HardwareProfile(name, round(ram_gb, 1), threads, round(vram_gb, 1), model, whisper)
