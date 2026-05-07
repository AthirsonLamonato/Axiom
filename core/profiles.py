"""
core/profiles.py — Gerenciamento de perfis de comportamento
"""

import logging
from core.config import Config


logger = logging.getLogger(__name__)


class ProfileManager:
    PROFILES = {
        "work": {
            "description": "Modo trabalho — respostas técnicas e diretas",
            "tts_rate": 175,
            "style": "technical",
        },
        "casual": {
            "description": "Modo casual — mais leve e conversacional",
            "tts_rate": 160,
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

    def switch(self, profile: str) -> str:
        if profile not in self.PROFILES:
            return f"Perfil '{profile}' não existe. Opções: {', '.join(self.PROFILES)}"
        self._active = profile
        self.config.set("profile.active", profile)
        desc = self.PROFILES[profile]["description"]
        logger.info(f"Perfil alterado para: {profile}")
        return desc

    def system_prompt(self) -> str:
        base = self.config.get("ai.system_prompt", "Você é Axiom, assistente pessoal técnico.")
        if self._active == "casual":
            return base + "\nResponda de forma mais descontraída e amigável."
        return base
