"""
input/stt.py — Speech-to-Text com Whisper
Dois modos:
  - Wake word via openWakeWord (modelo customizável, sem API key)
  - Push-to-talk via ctrl+shift+space (fallback automático)
"""

import logging
import threading
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK = 1024
OWW_CHUNK = 1280            # openWakeWord espera janelas de 80ms a 16kHz
MAX_COMMAND_DURATION = 10   # segundos máximos de captura (failsafe)
CALIBRATION_DURATION = 1.5  # segundos para medir ruído ambiente
ENERGY_MULTIPLIER = 2.5     # limiar = noise_rms × este fator
MIN_ENERGY = 300.0           # limiar mínimo absoluto (evita calibração muito baixa)
SILENCE_CHUNKS = 18          # chunks silenciosos consecutivos para encerrar gravação

# Instância singleton — acessível para comandos de voz
_voice: Optional["VoiceInput"] = None


def get_instance() -> Optional["VoiceInput"]:
    return _voice


def init_voice(config) -> "VoiceInput":
    global _voice
    _voice = VoiceInput(config)
    return _voice


def calibrar_microfone(*_) -> str:
    """Comando de voz: recalibra o limiar de ruído ambiente."""
    if _voice is None:
        return "STT não inicializado. Inicie o modo voz primeiro."
    threshold = _voice.calibrate()
    return f"Calibração concluída. Limiar de energia ajustado para {threshold:.0f}."


# Mapa de nomes de idioma → código ISO 639-1
_LANG_MAP = {
    "português": "pt", "portugues": "pt", "portuguese": "pt", "pt": "pt",
    "inglês":    "en", "ingles":    "en", "english":    "en", "en": "en",
    "espanhol":  "es", "spanish":   "es", "es":         "es",
    "francês":   "fr", "frances":   "fr", "french":     "fr", "fr": "fr",
    "alemão":    "de", "alemao":    "de", "german":     "de", "de": "de",
    "italiano":  "it", "italian":   "it", "it":         "it",
    "japonês":   "ja", "japones":   "ja", "japanese":   "ja", "ja": "ja",
}


_LANG_DISPLAY = {
    "pt": "Português", "en": "Inglês", "es": "Espanhol",
    "fr": "Francês",   "de": "Alemão", "it": "Italiano", "ja": "Japonês",
}
_active_language: str = ""   # persiste troca de idioma mesmo sem _voice ativo


def switch_language(lang: str, *_) -> str:
    """Altera o idioma de reconhecimento de voz em tempo real."""
    global _active_language
    code = _LANG_MAP.get(lang.lower().strip(), lang.lower().strip())
    _active_language = code
    if _voice is not None:
        _voice.config.set("stt.language", code)
    return f"Idioma do STT alterado para: {_LANG_DISPLAY.get(code, code)} ({code})"


def current_language(*_) -> str:
    """Retorna o idioma atual de reconhecimento."""
    if _voice is not None:
        lang = _voice.config.get("stt.language", "pt")
    elif _active_language:
        lang = _active_language
    else:
        from core.config import Config
        lang = Config().get("stt.language", "pt")
    return f"Idioma atual: {_LANG_DISPLAY.get(lang, lang)} ({lang})"


class VoiceInput:
    """
    Seleciona automaticamente o modo de escuta:
    wake word via openWakeWord (se disponível),
    caso contrário push-to-talk.
    """

    def __init__(self, config):
        self.config = config
        self._whisper = self._load_whisper()
        self._pa = self._load_pyaudio()
        self._noise_threshold: float = config.get("stt.noise_threshold", MIN_ENERGY)

        if config.get("wake_word.enabled", True):
            self._mode = "wake_word"
            self._oww = self._load_openwakeword()
        else:
            self._mode = "push_to_talk"
            self._oww = None
            logger.info("Wake word desabilitado — usando push-to-talk (ctrl+shift+space)")

        # Calibração automática na inicialização (se habilitada)
        if config.get("stt.auto_calibrate", True):
            try:
                self.calibrate()
            except Exception as e:
                logger.warning("Calibração automática falhou: %s — usando limiar padrão", e)

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

    def _load_openwakeword(self):
        """
        Carrega openWakeWord. Usa modelo customizado se wake_word.model_path for definido
        (ex: um arquivo paçoca.onnx treinado), ou hey_jarvis como padrão.

        Para treinar um modelo "Paçoca": github.com/dscripka/openWakeWord#training
        """
        try:
            from openwakeword.model import Model
            model_path = self.config.get("wake_word.model_path", "")
            if model_path:
                oww = Model(wakeword_models=[model_path], inference_framework="onnx")
                logger.info(f"openWakeWord carregado: modelo customizado '{model_path}'")
            else:
                oww = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
                logger.info("openWakeWord carregado: modelo padrão 'hey_jarvis'")
            return oww
        except Exception as e:
            logger.warning(f"openWakeWord falhou ({e}) — usando push-to-talk")
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
        threshold = self.config.get("wake_word.sensitivity", 0.5)
        stream = self._pa.open(
            rate=SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=OWW_CHUNK,
        )
        try:
            while True:
                pcm = np.frombuffer(
                    stream.read(OWW_CHUNK, exception_on_overflow=False),
                    dtype=np.int16,
                )
                prediction = self._oww.predict(pcm)
                if any(v >= threshold for v in prediction.values()):
                    logger.debug("Wake word detectada: %s", prediction)
                    stream.stop_stream()
                    return self._capture_and_transcribe()
        finally:
            stream.stop_stream()
            stream.close()

    # ── Push-to-talk ───────────────────────────────────────────────────

    def _listen_push_to_talk(self) -> str:
        """Aguarda Enter no terminal, captura áudio e transcreve."""
        print("[Paçoca] Pressione Enter para falar...", end=" ", flush=True)
        input()
        print("gravando...", end=" ", flush=True)
        return self._capture_and_transcribe()

    # ── Calibração de ruído ────────────────────────────────────────────

    def calibrate(self) -> float:
        """Mede o ruído ambiente por CALIBRATION_DURATION segundos e ajusta o limiar."""
        import pyaudio
        print("[Paçoca] Calibrando microfone...", end=" ", flush=True)
        stream = self._pa.open(
            rate=SAMPLE_RATE, channels=1, format=pyaudio.paInt16,
            input=True, frames_per_buffer=CHUNK,
        )
        num_chunks = int(SAMPLE_RATE / CHUNK * CALIBRATION_DURATION)
        rms_values = []
        for _ in range(num_chunks):
            data = stream.read(CHUNK, exception_on_overflow=False)
            rms_values.append(self._rms(data))
        stream.stop_stream()
        stream.close()

        noise_floor = float(np.mean(rms_values)) if rms_values else MIN_ENERGY
        self._noise_threshold = max(noise_floor * ENERGY_MULTIPLIER, MIN_ENERGY)
        self.config.set("stt.noise_threshold", self._noise_threshold)
        print(f"ok (limiar: {self._noise_threshold:.0f})")
        logger.info("Calibração: noise_floor=%.1f threshold=%.1f", noise_floor, self._noise_threshold)
        return self._noise_threshold

    @staticmethod
    def _rms(audio_chunk: bytes) -> float:
        data = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(data ** 2))) if len(data) > 0 else 0.0

    # ── Transcrição ────────────────────────────────────────────────────

    def _capture_and_transcribe(self) -> str:
        import pyaudio

        language = self.config.get("stt.language", "pt")
        max_chunks = int(SAMPLE_RATE / CHUNK * MAX_COMMAND_DURATION)

        stream = self._pa.open(
            rate=SAMPLE_RATE, channels=1, format=pyaudio.paInt16,
            input=True, frames_per_buffer=CHUNK,
        )

        frames = []
        voice_started = False
        silence_count = 0

        try:
            for _ in range(max_chunks):
                chunk = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(chunk)
                energy = self._rms(chunk)

                if energy > self._noise_threshold:
                    voice_started = True
                    silence_count = 0
                elif voice_started:
                    silence_count += 1
                    if silence_count >= SILENCE_CHUNKS:
                        break  # fim da fala detectado
        finally:
            stream.stop_stream()
            stream.close()

        audio = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._whisper.transcribe(audio, language=language, vad_filter=True)
        text = " ".join(s.text for s in segments).strip()
        print(f"ok → '{text}'")
        logger.info("Transcrição: %r", text)
        return text

    def transcribe_file(self, path: str) -> str:
        language = self.config.get("stt.language", "pt")
        segments, _ = self._whisper.transcribe(path, language=language)
        return " ".join(s.text for s in segments).strip()

    def close(self):
        if self._pa:
            self._pa.terminate()


# ── Confirmação por voz ────────────────────────────────────────────────

def register_voice_confirmation_callback(voice_instance: "VoiceInput", tts_speak_fn) -> None:
    """
    Registra um callback de confirmação baseado em TTS+STT:
      1. Fala a pergunta de confirmação para o usuário
      2. Ouve a resposta por voz
      3. Retorna True se o usuário confirmar ("sim", "pode", "confirma", etc.)

    tts_speak_fn: callable(text: str) — fala o texto (ex: tts.speak)
    Chame esta função em main.py após inicializar STT e TTS em modo voz.
    """
    import threading

    _CONFIRM_WORDS = {"sim", "pode", "confirma", "ok", "yes", "certo", "claro"}
    _DENY_WORDS    = {"não", "nao", "cancela", "nega", "no", "para", "para aí"}

    def voice_confirm(action_name: str, detail: str) -> bool:
        question = f"Confirmar {action_name} {detail}? Diga sim ou não."
        try:
            tts_speak_fn(question)
        except Exception:
            pass

        # Ouve com timeout de 6 segundos
        result: list[bool] = []
        done = threading.Event()

        def listen():
            try:
                text = (voice_instance.listen_once(timeout=6) or "").lower().strip()
                words = set(text.split())
                if words & _CONFIRM_WORDS:
                    result.append(True)
                elif words & _DENY_WORDS:
                    result.append(False)
                else:
                    result.append(False)  # sem resposta clara → nega por segurança
            except Exception:
                result.append(False)
            finally:
                done.set()

        t = threading.Thread(target=listen, daemon=True)
        t.start()
        done.wait(timeout=8)

        decision = result[0] if result else False
        try:
            msg = "Confirmado." if decision else "Cancelado."
            tts_speak_fn(msg)
        except Exception:
            pass
        return decision

    from modules.intent import set_confirmation_callback
    set_confirmation_callback(voice_confirm)
    logger.info("Callback de confirmação por voz registrado")
