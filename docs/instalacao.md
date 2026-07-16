# Guia de Instalação Detalhado

> Para instalação rápida pelo código-fonte, veja o [README.md](../README.md).
> Este guia cobre instalação a partir do código-fonte em detalhe, incluindo modos parciais.

---

## 1. Requisitos

- Python 3.10+
- 8GB RAM recomendado para usar simultaneamente Ollama, Whisper e interface; sem GPU necessária
- Windows, Linux ou macOS

---

## 2. Modo texto mínimo (sem voz, sem janela de desktop)

Mais rápido para testar o projeto:

```bash
git clone https://github.com/AthirsonLamonato/Pacoca.git
cd Pacoca
pip install -r requirements-minimal.txt
python main.py --mode text --no-tts --no-overlay
```

---

## 3. Modo texto completo (TTS + janela de desktop + dashboard)

```bash
pip install -r requirements.txt
pip install fastapi "uvicorn[standard]" python-multipart   # dashboard web (opcional)
python main.py --mode text
```

**IA local (padrão, sem internet depois do download):**

```bash
# Instale o Ollama: https://ollama.com
ollama pull llama3
```

O `core/config.yaml` já usa `ai.provider: ollama`. Groq é apenas um fallback
opcional; para habilitá-lo, configure `GROQ_API_KEY` no `.env`.

**Memória semântica (opcional, gratuita)**: sem configurar nada, a busca de
memórias usa palavra-chave. Para busca por significado, configure
`GEMINI_API_KEY` no `.env` (free tier em https://aistudio.google.com/apikey)
ou rode `ollama pull nomic-embed-text` se já usa Ollama. Detalhes em
[configuracao.md](configuracao.md#ai).

---

## 4. Modo voz (STT + wake word)

```bash
pip install -r requirements.txt
pip install -r requirements-voice.txt
```

**Windows:** o PyAudio 0.2.14 possui wheel oficial para Python 3.12; não use
`pipwin`.

```bash
pip install "pyaudio>=0.2.14"
```

**Linux:**

```bash
sudo apt install portaudio19-dev
pip install pyaudio
```

`faster-whisper` baixa o modelo Whisper na primeira execução. O `setup.bat`
baixa os artefatos ONNX do `hey_jarvis`; a inicialização também tenta repará-los
se estiverem ausentes. Para treinar um modelo "Paçoca" customizado, consulte
https://github.com/dscripka/openWakeWord#training.

```bash
python main.py --mode voice
```

Se `wake_word.enabled: false` no config, o modo voz usa push-to-talk
(`ctrl+shift+space`) em vez de detecção contínua.

---

## 5. Loopback de áudio (transcrição do sistema, não só microfone)

**Windows:**

```bash
pip install pyaudiowpatch
```

**Linux:** usa PulseAudio monitor source nativamente, sem dependência extra.

Comando de voz: `começa a transcrição do sistema`.

---

## 6. Recursos opcionais

| Recurso | Instalação |
|---|---|
| Clipboard por voz | `pip install pyperclip` |
| OCR de tela | `pip install pytesseract Pillow` + instalar Tesseract no sistema |
| Controle de volume (Windows) | `pip install pycaw comtypes` |
| Controle de brilho (Windows) | `pip install wmi` |
| Voz mais natural (offline) | `pip install TTS` (Coqui, ~1.5GB de modelos) |
| Identificação de falantes | `pip install pyannote.audio` + token HuggingFace + aceitar termos em https://huggingface.co/pyannote/speaker-diarization-3.1 |
| Armazenamento seguro de chaves | `pip install keyring` (já em requirements.txt) |
| Google Calendar / Drive | `pip install google-auth google-auth-oauthlib google-api-python-client` (já em requirements.txt) — requer `core/credentials.json` do Google Cloud Console |

---

## 7. Rodar os testes

```bash
pip install pytest
pytest tests/ -v
```

Testes que exigem hardware real, microfone ou download de modelo são pulados por
padrão. Para rodar o conjunto de voz:

```bash
pytest tests/ -v -m integration
```

---

## 8. Setup automatizado

```bash
# Windows
setup.bat

# Linux / Mac
bash setup.sh
```

Ou o wizard interativo:

```bash
python setup_wizard.py
```

---

## 9. Variáveis de ambiente

Crie um `.env` na raiz do projeto:

```
GROQ_API_KEY=sua_chave_aqui
GROQ_MODEL=llama-3.1-8b-instant
GEMINI_API_KEY=sua_chave_aqui   # opcional — habilita memória semântica
```

Veja a lista completa em [configuracao.md](configuracao.md#variáveis-de-ambiente-env).
