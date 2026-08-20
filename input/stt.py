"""
input/stt.py — Speech-to-Text com Whisper
Dois modos:
  - Wake word via openWakeWord (modelo customizável, sem API key)
  - Push-to-talk via ctrl+shift+space (fallback automático)
"""

import contextlib
from collections import deque
import logging
import os
import re
import threading
import unicodedata
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


def ensure_default_wakeword_model(download: bool = False) -> str | None:
    """Retorna o modelo ONNX ``hey_jarvis`` quando todos os artefatos existem.

    O pacote openWakeWord publica apenas os caminhos dos modelos; os arquivos
    precisam ser baixados separadamente. Centralizar essa verificacao evita que
    o diagnostico anuncie o wake word como pronto quando o modo de voz cairia
    silenciosamente para push-to-talk.
    """
    try:
        import openwakeword

        model_paths = openwakeword.get_pretrained_model_paths("onnx")
        jarvis_path = next(
            (path for path in model_paths if "hey_jarvis" in os.path.basename(path)),
            None,
        )
        if not jarvis_path:
            return None

        model_dir = os.path.dirname(jarvis_path)
        required = [
            jarvis_path,
            os.path.join(model_dir, "melspectrogram.onnx"),
            os.path.join(model_dir, "embedding_model.onnx"),
        ]
        if download and not all(os.path.isfile(path) for path in required):
            from openwakeword.utils import download_models

            download_models(["hey_jarvis"])
        return jarvis_path if all(os.path.isfile(path) for path in required) else None
    except Exception as exc:
        logger.debug("Nao foi possivel preparar o modelo Hey Jarvis: %s", exc)
        return None


@contextlib.contextmanager
def _suppress_native_audio_logs():
    """
    Silencia o log que libs nativas (ALSA/JACK no Linux) escrevem direto no
    file descriptor de stderr ao inicializar o PyAudio — não é um warning do
    Python, então `logging`/`warnings` não alcança. Comum em WSL/containers
    sem placa de som real; inofensivo, só ruído.
    """
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        saved_stderr_fd = os.dup(2)
        os.dup2(devnull_fd, 2)
    except Exception:
        yield
        return
    try:
        yield
    finally:
        os.dup2(saved_stderr_fd, 2)
        os.close(devnull_fd)
        os.close(saved_stderr_fd)

SAMPLE_RATE = 16000
CHUNK = 1024
OWW_CHUNK = 1280            # openWakeWord espera janelas de 80ms a 16kHz
MAX_COMMAND_DURATION = 10   # segundos máximos de captura (failsafe)
CALIBRATION_DURATION = 1.5  # segundos para medir ruído ambiente
ENERGY_MULTIPLIER = 2.5     # limiar = noise_rms × este fator
MIN_ENERGY = 300.0           # limiar mínimo absoluto (evita calibração muito baixa)
SILENCE_CHUNKS = 18          # chunks silenciosos consecutivos para encerrar gravação
PRE_SPEECH_TIMEOUT = 3.0     # tempo máximo aguardando o usuário começar a falar
PREROLL_CHUNKS = 4           # preserva ~250 ms antes da fala detectada

# Instância singleton — acessível para comandos de voz
_voice: Optional["VoiceInput"] = None
_voice_init_lock = threading.Lock()


def get_instance() -> Optional["VoiceInput"]:
    return _voice


def init_voice(config) -> "VoiceInput":
    global _voice
    with _voice_init_lock:
        if _voice is None:
            _voice = VoiceInput(config)
    return _voice


def _is_wake_phrase_only(text: str) -> bool:
    normalized = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized in {"hey jarvis", "ei jarvis", "hey javis", "ei javis", "jarvis", "javis"}


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
        self._push_to_talk_event = threading.Event()
        self._push_to_talk_hotkey_enabled = False
        self._capture_lock = threading.Lock()
        self._activation_callback = None
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
        local_only = bool(self.config.get("stt.local_files_only", True))
        try:
            model = WhisperModel(
                model_size,
                device=device,
                compute_type="int8",
                local_files_only=local_only,
            )
        except Exception:
            if not local_only:
                raise
            logger.info("Modelo Whisper ausente no cache; baixando uma vez")
            model = WhisperModel(model_size, device=device, compute_type="int8")
        logger.info(f"Whisper carregado: modelo={model_size} device={device}")
        return model

    def _load_pyaudio(self):
        import pyaudio
        with _suppress_native_audio_logs():
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
            import warnings
            from openwakeword.model import Model
            model_path = self.config.get("wake_word.model_path", "")
            # onnxruntime sempre tenta CUDAExecutionProvider antes do fallback
            # para CPU e avisa via warnings.warn — irrelevante neste projeto,
            # que roda em CPU por design (ver CLAUDE.md).
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                if model_path:
                    framework = "onnx" if str(model_path).lower().endswith(".onnx") else "tflite"
                    oww = Model(
                        wakeword_models=[model_path],
                        inference_framework=framework,
                    )
                    logger.info(f"openWakeWord carregado: modelo customizado '{model_path}'")
                else:
                    default_path = ensure_default_wakeword_model(download=True)
                    if not default_path:
                        raise RuntimeError("modelo hey_jarvis e artefatos ONNX ausentes")
                    oww = Model(
                        wakeword_models=[default_path],
                        inference_framework="onnx",
                    )
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

    def enable_push_to_talk_hotkey(self, enabled: bool = True) -> None:
        """Informa se Ctrl+Shift+Space foi registrado pelo gerenciador global."""
        self._push_to_talk_hotkey_enabled = enabled

    def request_push_to_talk(self) -> None:
        """Acorda o loop de voz para capturar um comando imediatamente."""
        self._push_to_talk_event.set()

    def set_activation_callback(self, callback) -> None:
        """Registra aviso chamado assim que wake word/PTT ativa a captura."""
        self._activation_callback = callback

    def _notify_activation(self) -> None:
        callback = getattr(self, "_activation_callback", None)
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.warning("Callback de ativação falhou", exc_info=True)

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
                if self._push_to_talk_event.is_set():
                    self._push_to_talk_event.clear()
                    stream.stop_stream()
                    self._notify_activation()
                    return self._capture_and_transcribe()
                pcm = np.frombuffer(
                    stream.read(OWW_CHUNK, exception_on_overflow=False),
                    dtype=np.int16,
                )
                prediction = self._oww.predict(pcm)
                if any(v >= threshold for v in prediction.values()):
                    logger.debug("Wake word detectada: %s", prediction)
                    stream.stop_stream()
                    self._notify_activation()
                    return self._capture_and_transcribe()
        finally:
            stream.stop_stream()
            stream.close()

    # ── Push-to-talk ───────────────────────────────────────────────────

    def _listen_push_to_talk(self) -> str:
        """Aguarda o atalho global; usa Enter quando o hook não está disponível."""
        if self._push_to_talk_hotkey_enabled:
            print("[Paçoca] Pressione Ctrl+Shift+Space para falar...", end=" ", flush=True)
            self._push_to_talk_event.wait()
            self._push_to_talk_event.clear()
        else:
            print("[Paçoca] Pressione Enter para falar...", end=" ", flush=True)
            input()
        print("gravando...", end=" ", flush=True)
        self._notify_activation()
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

    def _capture_and_transcribe(
        self,
        max_duration: float | None = None,
        cue: bool = True,
        pre_speech_timeout: float | None = None,
        on_speech_start=None,
    ) -> str:
        """Serializa o acesso ao microfone e executa uma captura completa."""
        with self._capture_lock:
            return self._capture_and_transcribe_unlocked(
                max_duration=max_duration,
                cue=cue,
                pre_speech_timeout=pre_speech_timeout,
                on_speech_start=on_speech_start,
            )

    def _play_ready_cue(self) -> None:
        if not self.config.get("stt.beep_enabled", True):
            return
        try:
            if os.name == "nt":
                import winsound

                winsound.Beep(880, 120)
            else:
                print("\a", end="", flush=True)
        except Exception:
            logger.debug("Sinal sonoro de captura indisponível", exc_info=True)

    def _capture_and_transcribe_unlocked(
        self,
        max_duration: float | None = None,
        cue: bool = True,
        pre_speech_timeout: float | None = None,
        on_speech_start=None,
    ) -> str:
        import pyaudio

        language = self.config.get("stt.language", "pt")
        duration = max_duration or MAX_COMMAND_DURATION
        max_chunks = int(SAMPLE_RATE / CHUNK * duration)
        speech_timeout = PRE_SPEECH_TIMEOUT if pre_speech_timeout is None else max(0.2, float(pre_speech_timeout))
        speech_start_chunks = min(max_chunks, int(SAMPLE_RATE / CHUNK * speech_timeout))

        if cue:
            self._play_ready_cue()

        stream = self._pa.open(
            rate=SAMPLE_RATE, channels=1, format=pyaudio.paInt16,
            input=True, frames_per_buffer=CHUNK,
        )

        frames = []
        pre_roll = deque(maxlen=PREROLL_CHUNKS)
        voice_started = False
        voiced_chunks = 0
        silence_count = 0

        try:
            for index in range(max_chunks):
                chunk = stream.read(CHUNK, exception_on_overflow=False)
                energy = self._rms(chunk)

                if energy > self._noise_threshold:
                    if not voice_started:
                        frames.extend(pre_roll)
                        if on_speech_start is not None:
                            try:
                                on_speech_start()
                            except Exception:
                                logger.debug("Callback de início de fala falhou", exc_info=True)
                    voice_started = True
                    voiced_chunks += 1
                    silence_count = 0
                    frames.append(chunk)
                elif voice_started:
                    frames.append(chunk)
                    silence_count += 1
                    if silence_count >= SILENCE_CHUNKS:
                        break  # fim da fala detectado
                else:
                    pre_roll.append(chunk)
                    if index + 1 >= speech_start_chunks:
                        break
        finally:
            stream.stop_stream()
            stream.close()

        # Não chama o Whisper para silêncio/ruído curto. Além de economizar
        # vários segundos no CPU, isso evita alucinações como comandos do
        # Spotify quando ninguém falou nada.
        min_voiced_chunks = max(2, int(SAMPLE_RATE / CHUNK * 0.18))
        if not voice_started or voiced_chunks < min_voiced_chunks:
            print("nenhuma fala detectada")
            logger.info("Captura ignorada: fala insuficiente (%d chunks)", voiced_chunks)
            return ""

        audio = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._whisper.transcribe(
            audio,
            language=language,
            vad_filter=True,
            beam_size=int(self.config.get("stt.beam_size", 2)),
            initial_prompt=self.config.get(
                "stt.initial_prompt",
                "Comandos para Paçoca: Spotify, Chrome, navegador, volume, pausar, continuar, próxima música.",
            ),
            condition_on_previous_text=False,
        )
        text = " ".join(s.text for s in segments).strip()
        if _is_wake_phrase_only(text):
            print("wake word repetida; aguardando o comando")
            logger.info("Transcrição ignorada por conter apenas a wake word: %r", text)
            return ""
        print(f"ok → '{text}'")
        logger.info("Transcrição: %r", text)
        return text

    def listen_once(
        self,
        timeout: float = 6.0,
        *,
        announce_activation: bool = False,
        pre_speech_timeout: float | None = None,
        activate_on_speech: bool = False,
    ) -> str:
        """
        Captura e transcreve um único utterance com tempo máximo de `timeout` segundos.

        Em seguimento hands-free, ``activate_on_speech`` chama o callback
        somente quando a energia de voz realmente começa. Isso permite ouvir
        a resposta e fazer barge-in sem cortar o TTS antes de o usuário falar.
        O comportamento antigo, com ativação imediata, permanece disponível
        quando ``announce_activation=True`` e ``activate_on_speech=False``.
        """
        if announce_activation and not activate_on_speech:
            self._notify_activation()
        return self._capture_and_transcribe(
            max_duration=timeout,
            cue=not announce_activation,
            pre_speech_timeout=pre_speech_timeout,
            on_speech_start=(self._notify_activation if activate_on_speech else None),
        )

    def transcribe_file(self, path: str) -> str:
        language = self.config.get("stt.language", "pt")
        segments, _ = self._whisper.transcribe(path, language=language)
        return " ".join(s.text for s in segments).strip()

    def close(self):
        global _voice
        if self._pa:
            self._pa.terminate()
        with _voice_init_lock:
            if _voice is self:
                _voice = None


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
