"""
core/config.py — Carregamento e acesso à configuração via config.yaml
Suporta notação de pontos: config.get("tts.enabled")
"""

import os
import yaml
from typing import Any


CONFIG_PATH = (
    os.environ.get("PACOCA_CONFIG_PATH")
    or os.environ.get("AXIOM_CONFIG_PATH")  # retrocompatibilidade com builds antigos
    or os.path.join(os.path.dirname(__file__), "config.yaml")
)
LOCAL_CONFIG_PATH = os.environ.get("PACOCA_CONFIG_LOCAL_PATH")


def _deep_merge(base: dict, override: dict) -> dict:
    """Mescla dicionários sem apagar chaves irmãs da configuração base."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


class Config:
    def __init__(self, path: str = CONFIG_PATH, local_path: str | None = None):
        self._path = path
        self._local_path = (
            local_path
            or LOCAL_CONFIG_PATH
            or os.path.join(os.path.dirname(path), "config.local.yaml")
        )
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
        if os.path.exists(self._local_path):
            with open(self._local_path, "r", encoding="utf-8") as f:
                local_data = yaml.safe_load(f) or {}
            if not isinstance(local_data, dict):
                raise ValueError("Config local deve conter um objeto YAML no nível raiz.")
            _deep_merge(self._data, local_data)

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
