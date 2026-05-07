"""
input/stt.py — Speech-to-Text com Whisper + Wake Word via Porcupine
Fluxo: escuta contínua → detecta wake word → captura comando → transcreve
"""

import logging
import numpy as np
import time

logger = logging.getLogger(__name__)

# Duração da captura de comando após wake word (segundos)
COMMAND_DURATION = 5
SAMPLE_RATE = 16000
CHUNK = 1024


class VoiceInput:
    def __init__(self, config):
        self.config = config
        self._pa = None
        self._porcupine = None
        self._whisper = None
        self._init()

    def _init(self):
        try:
            import pvporcupine
            import pyaudio
            from faster_whisper import WhisperModel

            keyword = self.config.get("wake_word.keyword", "axiom")
            sensitivity = self.config.get("wake_word.sensitivity", 0.5)
            model_size = self.config.get("stt.model", "base")
            device = self.config.get("stt.device", "cpu")

            self._porcupine = pvporcupine.create(
                keywords=[keyword],
                sensitivities=[sensitivity],
            )
            self._pa = pyaudio.PyAudio()
            self._whisper = WhisperModel(model_size, device=device, compute_type="int8")
            logger.info(f"STT inicializado | Modelo: {model_size} | Wake word: {keyword}")

        except ImportError as e:
            logger.error(f"Dependência STT ausente: {e}")
            raise

    def listen_for_command(self) -> str:
        """
        Bloqueia até detectar a wake word,
        depois captura e transcreve o comando.
        Retorna a transcrição como string.
        """
        stream = self._pa.open(
            rate=self._porcupine.sample_rate,
            channels=1,
            format=self._pa.get_format_from_width(2),  # paInt16
            input=True,
            frames_per_buffer=self._porcupine.frame_length,
        )

        try:
            while True:
                pcm_bytes = stream.read(
                    self._porcupine.frame_length, exception_on_overflow=False
                )
                pcm = np.frombuffer(pcm_bytes, dtype=np.int16)

                keyword_index = self._porcupine.process(pcm)
                if keyword_index >= 0:
                    logger.debug("Wake word detectada")
                    stream.stop_stream()
                    return self._capture_and_transcribe()
        finally:
            stream.stop_stream()
            stream.close()

    def _capture_and_transcribe(self) -> str:
        """Captura áudio por COMMAND_DURATION segundos e transcreve com Whisper."""
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

        print("[Axiom] Ouvindo...", end=" ", flush=True)
        for _ in range(num_chunks):
            frames.append(stream.read(CHUNK, exception_on_overflow=False))
        stream.stop_stream()
        stream.close()
        print("ok")

        audio = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32)
        audio /= 32768.0  # normaliza para [-1, 1]

        segments, _ = self._whisper.transcribe(
            audio,
            language=language,
            vad_filter=True,  # ignora silêncio
        )
        text = " ".join(s.text for s in segments).strip()
        logger.info(f"Transcrição: {text!r}")
        return text

    def transcribe_file(self, path: str) -> str:
        """Transcreve um arquivo de áudio diretamente."""
        language = self.config.get("stt.language", "pt")
        segments, _ = self._whisper.transcribe(path, language=language)
        return " ".join(s.text for s in segments).strip()

    def close(self):
        if self._porcupine:
            self._porcupine.delete()
        if self._pa:
            self._pa.terminate()
