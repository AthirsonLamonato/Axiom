"""
input/stt.py — Speech-to-Text com Whisper
Dois modos:
  - Wake word via pvporcupine (requer PICOVOICE_ACCESS_KEY)
  - Push-to-talk via ctrl+shift+space (fallback automático)
"""

import logging
import threading
import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK = 1024
COMMAND_DURATION = 5  # segundos de captura após ativação


class VoiceInput:
    """
    Seleciona automaticamente o modo de escuta:
    wake word se pvporcupine + access_key disponíveis,
    caso contrário push-to-talk.
    """

    def __init__(self, config):
        self.config = config
        self._whisper = self._load_whisper()
        self._pa = self._load_pyaudio()

        access_key = config.get("wake_word.access_key", "")
        if access_key:
            self._mode = "wake_word"
            self._porcupine = self._load_porcupine(access_key)
        else:
            self._mode = "push_to_talk"
            self._porcupine = None
            logger.info("pvporcupine sem access_key — usando push-to-talk (ctrl+shift+space)")

    def _load_whisper(self):
        from faster_whisper import WhisperModel
        model_size = self.config.get("stt.model", "base")
        device = self.config.get("stt.device", "cpu")
        model = WhisperModel(model_size, device=device, compute_type="int8")
        logger.info(f"Whisper carregado: modelo={model_size} device={device}")
        return model

    def _load_pyaudio(self):
        import pyaudio
        pa = pyaudio.PyAudio()
        logger.info("PyAudio inicializado")
        return pa

    def _load_porcupine(self, access_key: str):
        try:
            import pvporcupine
            keyword = self.config.get("wake_word.keyword", "porcupine")
            sensitivity = self.config.get("wake_word.sensitivity", 0.5)
            porcupine = pvporcupine.create(
                access_key=access_key,
                keywords=[keyword],
                sensitivities=[sensitivity],
            )
            logger.info(f"pvporcupine carregado: keyword={keyword}")
            return porcupine
        except Exception as e:
            logger.warning(f"pvporcupine falhou ({e}) — usando push-to-talk")
            self._mode = "push_to_talk"
            return None

    # ── Interface principal ────────────────────────────────────────────

    def listen_for_command(self) -> str:
        """Bloqueia até receber um comando (via wake word ou push-to-talk)."""
        if self._mode == "wake_word":
            return self._listen_wake_word()
        return self._listen_push_to_talk()

    # ── Wake word ──────────────────────────────────────────────────────

    def _listen_wake_word(self) -> str:
        import pyaudio
        stream = self._pa.open(
            rate=self._porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self._porcupine.frame_length,
        )
        try:
            while True:
                pcm = np.frombuffer(
                    stream.read(self._porcupine.frame_length, exception_on_overflow=False),
                    dtype=np.int16,
                )
                if self._porcupine.process(pcm) >= 0:
                    logger.debug("Wake word detectada")
                    stream.stop_stream()
                    return self._capture_and_transcribe()
        finally:
            stream.stop_stream()
            stream.close()

    # ── Push-to-talk ───────────────────────────────────────────────────

    def _listen_push_to_talk(self) -> str:
        """Aguarda ctrl+shift+space, captura e transcreve."""
        import keyboard

        print("[Axiom] Pressione ctrl+shift+space para falar...", end=" ", flush=True)

        event = threading.Event()
        keyboard.add_hotkey("ctrl+shift+space", event.set, suppress=True)
        event.wait()
        keyboard.remove_hotkey("ctrl+shift+space")

        print("gravando...", end=" ", flush=True)
        return self._capture_and_transcribe()

    # ── Transcrição ────────────────────────────────────────────────────

    def _capture_and_transcribe(self) -> str:
        import pyaudio

        language = self.config.get("stt.language", "pt")
        frames = []
        num_chunks = int(SAMPLE_RATE / CHUNK * COMMAND_DURATION)

        stream = self._pa.open(
            rate=SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=CHUNK,
        )
        for _ in range(num_chunks):
            frames.append(stream.read(CHUNK, exception_on_overflow=False))
        stream.stop_stream()
        stream.close()

        audio = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._whisper.transcribe(audio, language=language, vad_filter=True)
        text = " ".join(s.text for s in segments).strip()
        print(f"ok → '{text}'")
        logger.info(f"Transcrição: {text!r}")
        return text

    def transcribe_file(self, path: str) -> str:
        language = self.config.get("stt.language", "pt")
        segments, _ = self._whisper.transcribe(path, language=language)
        return " ".join(s.text for s in segments).strip()

    def close(self):
        if self._porcupine:
            self._porcupine.delete()
        if self._pa:
            self._pa.terminate()
