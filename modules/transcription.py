"""
modules/transcription.py — Transcrição de reuniões em tempo real
Captura do microfone (e opcionalmente loopback do sistema).
"""

import logging
import threading
import time
import os
from datetime import datetime

logger = logging.getLogger(__name__)

_session: "TranscriptionSession | None" = None


class TranscriptionSession:
    def __init__(self, config):
        self.config = config
        self._chunks: list[str] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._start_time = None

    def start(self):
        if self._running:
            return "Transcrição já está em andamento."
        self._running = True
        self._start_time = datetime.now()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Transcrição iniciada")
        return f"Transcrição iniciada às {self._start_time.strftime('%H:%M:%S')}."

    def stop(self) -> str:
        if not self._running:
            return "Nenhuma transcrição em andamento."
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        path = self._save()
        logger.info(f"Transcrição encerrada. Salva em: {path}")
        return f"Transcrição encerrada. Salva em {path}."

    def show_last(self) -> str:
        if not self._chunks:
            return "Nenhum conteúdo transcrito ainda."
        return "\n".join(self._chunks[-20:])  # últimas 20 linhas

    def full_text(self) -> str:
        return "\n".join(self._chunks)

    def _loop(self):
        """Loop principal: captura áudio em blocos e transcreve."""
        try:
            import pyaudio
            import numpy as np
            from faster_whisper import WhisperModel

            model_size = self.config.get("stt.model", "base")
            device = self.config.get("stt.device", "cpu")
            language = self.config.get("stt.language", "pt")

            model = WhisperModel(model_size, device=device, compute_type="int8")
            pa = pyaudio.PyAudio()
            sample_rate = 16000
            chunk_size = 1024
            # Captura em blocos de 10 segundos
            capture_secs = 10
            num_chunks = int(sample_rate / chunk_size * capture_secs)

            stream = pa.open(
                rate=sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=chunk_size,
            )

            print("[Axiom] Transcrevendo... (fale normalmente)")
            while self._running:
                frames = [stream.read(chunk_size, exception_on_overflow=False)
                          for _ in range(num_chunks)]
                audio = (
                    np.frombuffer(b"".join(frames), dtype=np.int16)
                    .astype(np.float32) / 32768.0
                )
                segments, _ = model.transcribe(audio, language=language, vad_filter=True)
                text = " ".join(s.text for s in segments).strip()
                if text:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    line = f"[{timestamp}] {text}"
                    self._chunks.append(line)
                    print(f"  {line}")

            stream.stop_stream()
            stream.close()
            pa.terminate()

        except ImportError as e:
            logger.error(f"Dependência ausente para transcrição: {e}")
            self._chunks.append(f"[ERRO] {e}")
            self._running = False

    def _save(self) -> str:
        from storage.file_store import save_transcription
        return save_transcription(self.full_text(), self._start_time)


# ── Interface pública (chamada pelo orchestrator) ─────────────────────

def start(*_) -> str:
    global _session
    from core.config import Config
    config = Config()
    _session = TranscriptionSession(config)
    return _session.start()


def stop(*_) -> str:
    global _session
    if _session is None:
        return "Nenhuma transcrição em andamento."
    result = _session.stop()
    _session = None
    return result


def show_last(*_) -> str:
    if _session is None:
        from storage.file_store import load_last_transcription
        text = load_last_transcription()
        return text if text else "Nenhuma transcrição disponível."
    return _session.show_last()
