"""
core/profiles.py — Gerenciamento de perfis de comportamento
"""

import logging
from typing import Optional
from core.config import Config


logger = logging.getLogger(__name__)

# Singleton — compartilhado entre Orchestrator e comandos de voz
_manager: Optional["ProfileManager"] = None


def _get_manager() -> "ProfileManager":
    global _manager
    if _manager is None:
        _manager = ProfileManager(Config())
    return _manager


def init_manager(config: Config) -> "ProfileManager":
    """Inicializa o singleton com o config do Orchestrator."""
    global _manager
    _manager = ProfileManager(config)
    return _manager


class ProfileManager:
    PROFILES = {
        "work": {
            "description": "Perfil trabalho ativado — respostas técnicas e diretas.",
            "tts_rate": 175,
            "tts_volume": 0.9,
            "style": "technical",
        },
        "casual": {
            "description": "Perfil casual ativado — mais leve e conversacional.",
            "tts_rate": 160,
            "tts_volume": 0.85,
            "style": "friendly",
        },
        "focus": {
            "description": "Perfil foco ativado — respostas concisas, sem distrações.",
            "tts_rate": 150,
            "tts_volume": 0.75,
            "style": "concise",
        },
        "meeting": {
            "description": "Perfil reunião ativado — transcrição recomendada, respostas formais.",
            "tts_rate": 145,
            "tts_volume": 0.7,
            "style": "formal",
        },
        "night": {
            "description": "Perfil noturno ativado — volume reduzido, respostas amigáveis.",
            "tts_rate": 155,
            "tts_volume": 0.5,
            "style": "friendly",
        },
    }

    def __init__(self, config: Config):
        self.config = config
        self._active = config.get("profile.active", "work")

    @property
    def active(self) -> str:
        return self._active

    @property
    def style(self) -> str:
        return self.PROFILES.get(self._active, {}).get("style", "technical")

    @property
    def tts_rate(self) -> int:
        return self.PROFILES.get(self._active, {}).get("tts_rate", 175)

    @property
    def tts_volume(self) -> float:
        return self.PROFILES.get(self._active, {}).get("tts_volume", 0.9)

    def switch(self, profile: str) -> str:
        profile = profile.strip().lower()
        _aliases = {
            "trabalho": "work", "foco": "focus", "reuniao": "meeting",
            "reunião": "meeting", "noturno": "night", "noite": "night",
        }
        profile = _aliases.get(profile, profile)
        if profile not in self.PROFILES:
            opts = ", ".join(self.PROFILES)
            return f"Perfil '{profile}' não existe. Opções: {opts}"
        self._active = profile
        self.config.set("profile.active", profile)
        desc = self.PROFILES[profile]["description"]
        logger.info(f"Perfil alterado para: {profile}")
        return desc

    def system_prompt(self) -> str:
        base = self.config.get("ai.system_prompt", "Você é Axiom, assistente pessoal técnico.")
        addons = {
            "casual":  "\nResponda de forma descontraída e amigável.",
            "focus":   "\nSeja extremamente conciso. Máximo 2 frases por resposta.",
            "meeting": "\nUse linguagem formal. Mantenha respostas estruturadas.",
            "night":   "\nMantenha tom suave e tranquilo. Evite notificações desnecessárias.",
        }
        return base + addons.get(self._active, "")


# ── Comandos de voz (funções públicas chamadas pelo orchestrator) ──────

def switch_profile(profile: str, *_) -> str:
    return _get_manager().switch(profile)


def current_profile(*_) -> str:
    mgr = _get_manager()
    p = mgr.active
    desc = ProfileManager.PROFILES[p]["description"]
    return f"Perfil atual: {p}. {desc}"


def list_profiles(*_) -> str:
    lines = ["Perfis disponíveis:"]
    for name, data in ProfileManager.PROFILES.items():
        lines.append(f"  • {name}: {data['description']}")
    return "\n".join(lines)
