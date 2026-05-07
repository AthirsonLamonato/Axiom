"""
modules/transcription.py — Transcrição de reuniões em tempo real
Suporta microfone e loopback do sistema (Windows: pyaudiowpatch, Linux: PulseAudio).
Auto-save a cada 5 minutos.
"""

import logging
import threading
import time
import platform
from datetime import datetime

logger = logging.getLogger(__name__)

OS = platform.system()
_session: "TranscriptionSession | None" = None
AUTO_SAVE_INTERVAL = 300  # segundos


class TranscriptionSession:
    def __init__(self, config, source: str = "mic"):
        """
        source: 'mic' (microfone) | 'loopback' (áudio do sistema)
        """
        self.config = config
        self.source = source
        self._chunks: list = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._save_thread: threading.Thread | None = None
        self._start_time = None
        self._lock = threading.Lock()

    def start(self) -> str:
        if self._running:
            return "Transcrição já está em andamento."
        self._running = True
        self._start_time = datetime.now()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._save_thread = threading.Thread(target=self._auto_save_loop, daemon=True)
        self._save_thread.start()
        src = "microfone" if self.source == "mic" else "áudio do sistema"
        logger.info(f"Transcrição iniciada — fonte: {src}")
        return f"Transcrição iniciada às {self._start_time.strftime('%H:%M:%S')} ({src})."

    def stop(self) -> str:
        if not self._running:
            return "Nenhuma transcrição em andamento."
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        path = self._save()
        logger.info(f"Transcrição encerrada → {path}")
        return f"Transcrição encerrada. Salva em {path}."

    def show_last(self) -> str:
        with self._lock:
            if not self._chunks:
                return "Nenhum conteúdo transcrito ainda."
            return "\n".join(self._chunks[-20:])

    def full_text(self) -> str:
        with self._lock:
            return "\n".join(self._chunks)

    # ── Loop principal ─────────────────────────────────────────────────

    def _loop(self):
        try:
            import numpy as np
            from faster_whisper import WhisperModel

            model_size = self.config.get("stt.model", "base")
            device = self.config.get("stt.device", "cpu")
            language = self.config.get("stt.language", "pt")
            model = WhisperModel(model_size, device=device, compute_type="int8")

            stream, pa = self._open_stream()
            if stream is None:
                self._running = False
                return

            sample_rate = 16000
            chunk_size = 1024
            capture_secs = 10
            num_chunks = int(sample_rate / chunk_size * capture_secs)

            print(f"[Axiom] Transcrevendo ({self.source})... fale normalmente")

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
                    line = f"[{datetime.now().strftime('%H:%M:%S')}] {text}"
                    with self._lock:
                        self._chunks.append(line)
                    print(f"  {line}")

                    from output import overlay
                    overlay.show_message(line, duration_ms=3000)

            stream.stop_stream()
            stream.close()
            pa.terminate()

        except ImportError as e:
            logger.error(f"Dependência ausente: {e}")
            with self._lock:
                self._chunks.append(f"[ERRO] {e}")
            self._running = False

    def _open_stream(self):
        """Abre stream de áudio conforme a fonte configurada."""
        if self.source == "loopback":
            return self._open_loopback()
        return self._open_mic()

    def _open_mic(self):
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            stream = pa.open(
                rate=16000, channels=1,
                format=pyaudio.paInt16,
                input=True, frames_per_buffer=1024,
            )
            return stream, pa
        except Exception as e:
            logger.error(f"Erro ao abrir microfone: {e}")
            with self._lock:
                self._chunks.append(f"[ERRO microfone] {e}")
            return None, None

    def _open_loopback(self):
        """Captura áudio do sistema (loopback)."""
        if OS == "Windows":
            return self._open_loopback_windows()
        elif OS == "Linux":
            return self._open_loopback_linux()
        logger.warning("Loopback não suportado neste sistema. Usando microfone.")
        return self._open_mic()

    def _open_loopback_windows(self):
        try:
            import pyaudiowpatch as pyaudio
            pa = pyaudio.PyAudio()
            # Busca dispositivo WASAPI loopback do speaker padrão
            wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = pa.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

            if not default_speakers.get("isLoopbackDevice", False):
                # Encontra o dispositivo loopback correspondente
                for i in range(pa.get_device_count()):
                    d = pa.get_device_info_by_index(i)
                    if d.get("isLoopbackDevice") and default_speakers["name"] in d["name"]:
                        default_speakers = d
                        break

            stream = pa.open(
                rate=int(default_speakers["defaultSampleRate"]),
                channels=default_speakers["maxInputChannels"],
                format=pyaudio.paInt16,
                input=True,
                input_device_index=default_speakers["index"],
                frames_per_buffer=1024,
            )
            logger.info(f"Loopback WASAPI: {default_speakers['name']}")
            return stream, pa
        except Exception as e:
            logger.warning(f"Loopback Windows falhou ({e}). Usando microfone.")
            return self._open_mic()

    def _open_loopback_linux(self):
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            # Monitor source do PulseAudio — nome contém ".monitor"
            monitor_index = None
            for i in range(pa.get_device_count()):
                d = pa.get_device_info_by_index(i)
                if ".monitor" in d.get("name", "").lower():
                    monitor_index = i
                    break
            if monitor_index is None:
                raise RuntimeError("Nenhum monitor source encontrado. Configure o PulseAudio.")
            stream = pa.open(
                rate=16000, channels=1,
                format=pyaudio.paInt16,
                input=True, input_device_index=monitor_index,
                frames_per_buffer=1024,
            )
            logger.info("Loopback PulseAudio (monitor source) aberto")
            return stream, pa
        except Exception as e:
            logger.warning(f"Loopback Linux falhou ({e}). Usando microfone.")
            return self._open_mic()

    # ── Auto-save ─────────────────────────────────────────────────────

    def _auto_save_loop(self):
        while self._running:
            time.sleep(AUTO_SAVE_INTERVAL)
            if self._running and self._chunks:
                path = self._save(label="autosave")
                logger.info(f"Auto-save: {path}")
                from output.notifier import notify
                notify("Axiom", f"Transcrição salva automaticamente.")

    def _save(self, label: str = "") -> str:
        from storage.file_store import save_transcription
        return save_transcription(self.full_text(), self._start_time)


# ── Interface pública (chamada pelo orchestrator) ─────────────────────

def start(*args) -> str:
    global _session
    source = "loopback" if args and "sistema" in str(args[0]) else "mic"
    from core.config import Config
    _session = TranscriptionSession(Config(), source=source)
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
