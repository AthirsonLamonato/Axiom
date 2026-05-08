"""
output/tts.py — Text-to-Speech
Suporta pyttsx3 (offline, leve) e Coqui TTS (offline, mais natural).
"""

import logging
import threading

logger = logging.getLogger(__name__)


class TTS:
    def __init__(self, config):
        self.config = config
        self.enabled = config.get("tts.enabled", True)
        self.engine_name = config.get("tts.engine", "pyttsx3")
        self._engine = None
        self._lock = threading.Lock()

        if self.enabled:
            self._init()

    def _init(self):
        if self.engine_name == "pyttsx3":
            self._init_pyttsx3()
        elif self.engine_name == "coqui":
            self._init_coqui()

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            rate = self.config.get("tts.rate", 175)
            volume = self.config.get("tts.volume", 0.9)
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", rate)
            self._engine.setProperty("volume", volume)

            # Tenta selecionar voz em português
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
            logger.warning("Coqui TTS não instalado. Usando pyttsx3.")
            self.engine_name = "pyttsx3"
            self._init_pyttsx3()

    def speak(self, text: str):
        """Fala o texto em thread separada (não bloqueia)."""
        if not self.enabled or not text:
            return
        thread = threading.Thread(target=self._speak_sync, args=(text,), daemon=True)
        thread.start()

    def _speak_sync(self, text: str):
        with self._lock:
            try:
                if self.engine_name == "pyttsx3" and self._engine:
                    self._engine.say(text)
                    self._engine.runAndWait()
                elif self.engine_name == "coqui" and self._engine:
                    import tempfile, os
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        path = f.name
                    self._engine.tts_to_file(text=text, file_path=path)
                    # Reproduz o arquivo
                    import subprocess, platform
                    if platform.system() == "Windows":
                        subprocess.run(["powershell", "-c",
                                        f"(New-Object Media.SoundPlayer '{path}').PlaySync()"])
                    else:
                        subprocess.run(["aplay", path], capture_output=True)
                    os.unlink(path)
            except Exception as e:
                logger.error(f"Erro TTS: {e}")

    def set_rate(self, rate: int):
        if self.engine_name == "pyttsx3" and self._engine:
            self._engine.setProperty("rate", rate)

    def set_volume(self, volume: float):
        if self.engine_name == "pyttsx3" and self._engine:
            self._engine.setProperty("volume", volume)
