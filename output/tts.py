"""
output/tts.py — Text-to-Speech
Suporta edge-tts (recomendado), pyttsx3 (offline) e Coqui TTS (offline, mais natural).
"""

import logging
import re
import threading
import subprocess
import tempfile
import os
import platform
from typing import Generator

logger = logging.getLogger(__name__)

def _check_wsl() -> bool:
    try:
        from pathlib import Path
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False

IS_WSL = platform.system() == "Linux" and _check_wsl()


class TTS:
    def __init__(self, config):
        self.config = config
        self.enabled = config.get("tts.enabled", True)
        self.engine_name = config.get("tts.engine", "edge")
        self._engine = None
        self._lock = threading.Lock()

        if self.enabled:
            self._init()

    def _init(self):
        if self.engine_name == "edge":
            self._init_edge()
        elif self.engine_name == "pyttsx3":
            self._init_pyttsx3()
        elif self.engine_name == "coqui":
            self._init_coqui()

    def _init_edge(self):
        try:
            import edge_tts  # noqa: F401
            self.voice = self.config.get("tts.edge_voice", "pt-BR-FranciscaNeural")
            logger.info(f"TTS edge-tts inicializado (voz: {self.voice})")
        except ImportError:
            logger.warning("edge-tts não instalado. Usando pyttsx3. Instale com: pip install edge-tts")
            self.engine_name = "pyttsx3"
            self._init_pyttsx3()

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            rate = self.config.get("tts.rate", 175)
            volume = self.config.get("tts.volume", 0.9)
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", rate)
            self._engine.setProperty("volume", volume)
            voices = self._engine.getProperty("voices")
            for voice in voices:
                if "pt" in voice.id.lower() or "brazil" in voice.id.lower():
                    self._engine.setProperty("voice", voice.id)
                    break
            logger.info("TTS pyttsx3 inicializado")
        except ImportError:
            logger.warning("pyttsx3 não instalado. TTS desabilitado.")
            self.enabled = False

    def _init_coqui(self):
        try:
            from TTS.api import TTS as CoquiTTS
            self._engine = CoquiTTS("tts_models/pt/cv/vits")
            logger.info("TTS Coqui inicializado")
        except ImportError:
            logger.warning("Coqui TTS não instalado. Usando edge-tts.")
            self.engine_name = "edge"
            self._init_edge()

    def speak(self, text: str):
        """Fala o texto em thread separada (não bloqueia)."""
        if not self.enabled or not text:
            return
        thread = threading.Thread(target=self._speak_sync, args=(text,), daemon=True)
        thread.start()

    def _speak_sync(self, text: str):
        with self._lock:
            try:
                if self.engine_name == "edge":
                    self._speak_edge(text)
                elif self.engine_name == "pyttsx3" and self._engine:
                    self._engine.say(text)
                    self._engine.runAndWait()
                elif self.engine_name == "coqui" and self._engine:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        path = f.name
                    self._engine.tts_to_file(text=text, file_path=path)
                    self._play_audio(path)
                    os.unlink(path)
            except Exception as e:
                logger.error(f"Erro TTS: {e}")

    def _speak_edge(self, text: str):
        if IS_WSL or platform.system() == "Windows":
            # Usa Windows SAPI diretamente — sem arquivos, sem dependências
            self._speak_windows_sapi(text)
        else:
            self._speak_edge_file(text)

    def _speak_windows_sapi(self, text: str):
        """Fala usando o TTS nativo do Windows via PowerShell SAPI."""
        voice_hint = self.config.get("tts.edge_voice", "pt-BR-FranciscaNeural")
        lang = "pt" if "pt" in voice_hint.lower() else "en"
        safe_text = text.replace("'", "''").replace('"', '""')
        ps_script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$v = $s.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Culture -like '{lang}*' }} | Select-Object -First 1; "
            "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; "
            f"$s.Speak('{safe_text}');"
        )
        try:
            proc = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            # Aguarda no máximo 15s (texto longo) sem bloquear o loop principal
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        except Exception as e:
            logger.error(f"Erro Windows SAPI: {e}")

    def _speak_edge_file(self, text: str):
        """Fala usando edge-tts (Linux nativo, requer mpg123)."""
        import asyncio
        import edge_tts

        async def _run():
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                path = f.name
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(path)
            return path

        path = asyncio.run(_run())
        try:
            subprocess.run(["mpg123", "-q", path], capture_output=True)
        finally:
            os.unlink(path)

    def speak_stream(self, generator: Generator[str, None, None]):
        """
        Fala o texto de um gerador chunk por chunk, quebrando em frases.
        Permite TTS responsivo durante streaming do LLM — o usuário ouve
        a primeira frase antes que o LLM termine de gerar.
        """
        if not self.enabled:
            for _ in generator:  # drena o gerador
                pass
            return

        _SENT_END = re.compile(r'(?<=[.!?])\s+')
        buffer = ""

        def _flush(text: str):
            text = text.strip()
            if text:
                self._speak_sync(text)

        for chunk in generator:
            buffer += chunk
            # Divide em frases completas (mantém a última que pode estar incompleta)
            parts = _SENT_END.split(buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    _flush(sentence)
                buffer = parts[-1]

        _flush(buffer)

    def set_rate(self, rate: int):
        if self.engine_name == "pyttsx3" and self._engine:
            self._engine.setProperty("rate", rate)

    def set_volume(self, volume: float):
        if self.engine_name == "pyttsx3" and self._engine:
            self._engine.setProperty("volume", volume)
