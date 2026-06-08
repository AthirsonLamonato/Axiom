"""
core/config.py — Carregamento e acesso à configuração via config.yaml
Suporta notação de pontos: config.get("tts.enabled")
"""

import os
import yaml
from typing import Any


CONFIG_PATH = os.environ.get("AXIOM_CONFIG_PATH") or os.path.join(os.path.dirname(__file__), "config.yaml")


class Config:
    def __init__(self, path: str = CONFIG_PATH):
        self._path = path
        self._data: dict = {}
        self._load()

    def _load(self):
        if not os.path.exists(self._path):
            raise FileNotFoundError(
                f"[Config] Arquivo não encontrado: {self._path}\n"
                "O arquivo core/config.yaml é necessário para iniciar o Paçoca.\n"
                "Se você clonou o repositório, ele já deve estar presente.\n"
                "Caso contrário, verifique se está rodando a partir do diretório correto."
            )
        with open(self._path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Acessa valores com notação de pontos.
        Exemplo: config.get("tts.engine") → "pyttsx3"
        """
        keys = key.split(".")
        node = self._data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def set(self, key: str, value: Any):
        """Define um valor em runtime (não persiste no YAML)."""
        keys = key.split(".")
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    def all(self) -> dict:
        return self._data
