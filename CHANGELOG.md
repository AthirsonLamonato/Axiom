# Changelog

Todas as mudanças notáveis do projeto Paçoca são documentadas aqui.
Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [0.5.0] — 2026-05-08

### Alterado
- **Groq substitui Anthropic** como fallback cloud de IA — gratuito, sem cartão, OpenAI-compatible; `GROQ_API_KEY` (console.groq.com); modelo padrão `llama3-8b-8192`

### Adicionado
- **73 testes** (eram 36): `test_dispatch_chain.py`, `test_reminders.py`, `test_context.py`
- **WebSocket no dashboard** — endpoint `/ws/command` para respostas instantâneas; `/ws/events` para push em tempo real (lembretes, reuniões)
- **Editor visual de rotinas** no dashboard — CRUD com htmx, persistido no `config.yaml`
- **Autenticação no dashboard** — middleware de cookie + página de login; ativado por `web.password` no config
- **Scripts de instalação reescritos** — `setup.bat` / `setup.sh` usam `requirements.txt`, criam diretórios, rodam testes e baixam llama3
- **Build como executável** — `axiom.spec` (PyInstaller) + `build.bat` / `build.sh`
- `hooks/` — diretório requerido pelo `axiom.spec`

### Corrigido
- `web_server.py` — senha lida do `orchestrator.config` em vez de criar nova instância de Config
- `web_server.py` — variável `_server_orc` adicionada para persistir referência do orchestrator
- `main.py` — versão corrigida de `v0.1.0-alpha` para `v0.5.0`
- `.github/workflows/tests.yml` — Python atualizado para 3.9; adicionados `google-auth`, `fastapi`, `uvicorn` ao CI

### Removido
- Diretório órfão `{core,input,modules,output,storage,logs,data` (criado acidentalmente)

---

## [0.4.0] — 2026-05-08

### Adicionado
- **Dashboard web local** (FastAPI + htmx, porta 7755) com `--web` flag
- **Exportação para Obsidian** — transcrições, sumários, nota diária, anotações com frontmatter YAML
- **Comandos encadeados** — `dispatch_chain()` com conectores naturais ("e depois", "em seguida", "então") e detecção automática via "e"
- **Detector de reunião automático** — monitora Zoom/Teams/Slack/Webex via psutil; ativa perfil meeting e transcrição
- **TTS profile-aware** — rate e volume do TTS sincronizados ao trocar perfil por voz
- `web/app.py`, `web/__init__.py`, `modules/web_server.py`, `modules/meeting_detector.py`, `modules/obsidian.py`
- `_CHAIN_SEP`, `_CHAIN_AND`, `_matches_route()`, `_sync_tts_profile()` no orchestrator
- `TTS.set_volume()` em `output/tts.py`
- Seções `obsidian` e `web` no `config.yaml`
- `fastapi`, `uvicorn[standard]` como deps opcionais no `requirements.txt`

---

## [0.3.0] — 2026-05-07

### Adicionado
- **Memória contextual** — ring buffer (deque, maxlen=10) injetado no prompt do LLM; `storage/context.py`
- **Lembretes por voz** — horário absoluto ("às 15h") e relativo ("em 30 min"); `modules/reminders.py`
- **Clipboard por voz** — copiar texto/último resultado, ler e limpar; `modules/clipboard_tools.py`
- **OCR de tela** — `lê o texto na tela`, `salva screenshot`; `modules/screen_reader.py`
- **Multi-idioma STT** — troca PT/EN/ES/FR/DE/IT por voz; `switch_language()` em `input/stt.py`
- **Sumário de reunião estruturado** — 5 seções: resumo executivo, decisões, action items, pendências, próximos passos
- **Sumário de sessão** — `summarize_session()` gera bullet points do contexto atual

---

## [0.2.0] — 2026-05-07

### Adicionado
- **Calibração automática de ruído** — VAD por energia RMS; `calibrate()` e `_rms()` em `input/stt.py`
- **5 perfis dinâmicos** — work / casual / focus / meeting / night; `core/profiles.py` com singleton
- **Google Calendar** — ver agenda, próximo evento, criar evento por voz; `modules/calendar_integration.py`
- **Plugin system** — auto-scan de `plugins/`; hot-reload por voz; `core/plugin_loader.py`
- **Plugin de anotações** — `plugins/notes.py`; template em `plugins/_template.py`
- **Speaker diarization** — `pyannote.audio`; identificação de `[Falante 1]`, `[Falante 2]`…

---

## [0.1.0] — 2026-05-06

### Adicionado
- Boot completo com `core/logger.py`, `storage/db.py`, `modules/productivity.py`
- Modo texto e modo voz (push-to-talk `ctrl+shift+space`; wake word opcional via Porcupine)
- Overlay flutuante PyQt6 — estado (idle / listening / processing / speaking), histórico, fade animado
- Transcrição mic + loopback (WASAPI/PulseAudio) com auto-save a cada 5 min
- Dev tools: git por voz, abrir arquivo, ir para linha, explicar código via IA
- Pomodoro, relatório diário, rotinas com condições em YAML
- Backup local + Google Drive (OAuth)
- CI/CD com GitHub Actions (`tests.yml`)
