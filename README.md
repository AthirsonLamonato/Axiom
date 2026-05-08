# Paçoca

> Assistente pessoal inteligente de desktop — controle por voz ou texto, 100% open-source e gratuito.

![Version](https://img.shields.io/badge/version-v0.5.0-blue)
![Python](https://img.shields.io/badge/python-3.9+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Tests](https://img.shields.io/badge/tests-73%20passing-brightgreen)
![CI](https://github.com/AthirsonLamonato/Pacoca/actions/workflows/tests.yml/badge.svg)

Paçoca é um assistente de desktop estilo Jarvis — modular, expansível e capaz de rodar completamente offline em hardware modesto (4 GB RAM, CPU sem GPU).

---

## Download

**[⬇ Pacoca-v0.5.0-Windows.zip](https://github.com/AthirsonLamonato/Pacoca/releases/download/v0.5.0/Pacoca-v0.5.0-Windows.zip)** — Windows 64-bit · 175 MB · sem Python, sem pip install

> Extraia o ZIP, rode `Pacoca-Setup.exe` e siga as 4 etapas do assistente de instalação.

---

## Instalação

### Opção 1 — Executável (recomendado, apenas Windows)

1. Baixe `Pacoca-v0.5.0-Windows.zip` na [página de releases](https://github.com/AthirsonLamonato/Pacoca/releases/tag/v0.5.0)
2. Extraia em qualquer pasta
3. Execute `Pacoca-Setup.exe` — o wizard configura tudo automaticamente:
   - Baixa e instala o Ollama + modelo de IA
   - Configura `core/config.yaml`
   - Faz login com o Google (Calendar + Drive, opcional)
   - Cria atalho na área de trabalho apontando para `Pacoca/Pacoca.exe`

O `Pacoca.exe` traz todas as dependências Python bundled — PyQt6, faster-whisper, FastAPI, Google Auth e mais. **Não é necessário instalar Python ou qualquer pacote.**

### Opção 2 — A partir do código-fonte

```bash
git clone https://github.com/AthirsonLamonato/Pacoca.git
cd Paçoca
```

**Windows:**
```bat
setup.bat
```

**Linux / Mac:**
```bash
bash setup.sh
```

Ou manualmente:
```bash
pip install -r requirements.txt
pip install fastapi "uvicorn[standard]"
ollama pull llama3
```

---

## Executar

### Via executável

```
Pacoca/Pacoca.exe                         # modo voz (padrão)
Pacoca/Pacoca.exe --mode text --no-tts    # modo texto, sem voz
Pacoca/Pacoca.exe --web                   # com dashboard em localhost:7755
```

### Via Python (código-fonte)

```bash
# Modo texto — ideal para testar sem microfone
python main.py --mode text --no-tts --no-overlay

# Modo voz (push-to-talk por padrão)
python main.py

# Dashboard web (abre o browser em localhost:7755)
python main.py --web

# Editor de rotinas CLI
python main.py --edit-routines
```

---

## Funcionalidades

| Módulo | O que faz |
|---|---|
| **STT** | Transcrição via Whisper (`faster-whisper`). Calibração automática de ruído; VAD por energia RMS. Push-to-talk `ctrl+shift+space` por padrão; wake word via Porcupine se configurada |
| **Overlay** | Janela flutuante PyQt6: estado (idle / listening / processing / speaking), histórico dos 3 últimos comandos, fade animado. Toggle: `ctrl+shift+a` |
| **Transcrição** | Captura microfone ou loopback do sistema (Windows: WASAPI · Linux: PulseAudio). Auto-save a cada 5 min |
| **Resumo / IA** | Resumo e explicações via Ollama (local) com fallback para Anthropic API |
| **Pesquisa** | Roteamento automático: perguntas factuais/atuais → DuckDuckGo + IA; demais → LLM local |
| **Dev tools** | VS Code, abrir arquivo por nome, ir para linha, criar arquivo, git status/log/commit/push/pull/branch, rodar testes, explicar código via IA |
| **Rotinas** | Sequências configuráveis em YAML com condições (`weekday`, `weekend`, `morning`, `afternoon`, `evening`) |
| **Pomodoro** | Timer de foco com notificação e overlay ao término |
| **Produtividade** | Monitoramento de apps via psutil, relatório diário em Markdown |
| **Sistema** | Abrir/fechar apps, volume, brilho, listar processos (Windows + Linux) |
| **Segurança** | Confirmação antes de ações críticas, lista configurável |
| **Backup** | Local automático + Google Drive (opcional, OAuth via wizard) |
| **Perfis** | work / casual / focus / meeting / night — alteráveis por voz em tempo real |
| **Google Calendar** | Ver agenda do dia, próximo evento, adicionar eventos por voz |
| **Speaker diarization** | Identifica falantes na transcrição (`[Falante 1]`, `[Falante 2]`…) — requer `pyannote.audio` |
| **Plugin system** | Carregamento dinâmico em `plugins/`. Plugin de anotações incluso. Hot-reload por voz |
| **Memória contextual** | Histórico da sessão injetado no prompt do LLM para respostas coerentes |
| **Lembretes** | Notificações por voz — horário absoluto ("às 15h") ou relativo ("em 30 min") |
| **Clipboard** | Copiar texto/último resultado, ler e limpar área de transferência por voz |
| **OCR de tela** | Lê texto visível via pytesseract. Salva screenshots |
| **Multi-idioma STT** | Troca o idioma de reconhecimento por voz (PT, EN, ES, FR, DE…) |
| **Sumário de reunião** | Sumário estruturado: resumo executivo, decisões, action items e pendências |
| **Dashboard web** | Interface local (FastAPI + htmx + WebSocket) em `localhost:7755` — histórico, lembretes, envio de comandos em tempo real |
| **Editor de rotinas** | CRUD visual de rotinas no dashboard, persistido no `config.yaml` |
| **Obsidian** | Exporta transcrições, sumários e nota diária para qualquer vault Markdown |
| **Comandos encadeados** | "abre o VS Code e depois foco por 25 min" — múltiplos comandos em sequência |
| **Modo reunião auto** | Detecta Zoom/Teams/Slack via psutil; ativa perfil meeting e transcrição automaticamente |
| **TTS profile-aware** | Rate e volume do TTS sincronizados ao trocar perfil |
| **Banco de dados** | SQLite — histórico de comandos, sessões e transcrições |
| **TTS** | pyttsx3 (offline, leve) |

---

## Comandos disponíveis

### Sistema
```
abre o VS Code
abre o Chrome
fecha o Spotify
volume 70
aumenta o brilho / diminui o brilho
muta o som
lista processos
```

### Transcrição
```
começa a transcrever
começa a transcrever o sistema        ← loopback (áudio do speaker)
para a transcrição
mostra o que foi falado
```

### IA e pesquisa
```
resume o que foi falado
resumo detalhado
explica o que é recursão
pesquisa como funciona decorators em Python
busca na internet o clima de amanhã
```

### Dev tools
```
abre o arquivo main.py
vai para a linha 42
cria arquivo utils.py
explica o arquivo orchestrator.py
commit "feat: nova funcionalidade"
git push / git pull
o que mudou                           ← git status
mostra os últimos commits             ← git log
cria branch feature/nome
branch atual
roda os testes
```

### Rotinas e produtividade
```
modo trabalho
modo foco
fim do dia
executa rotina end_of_day
foco por 25 min                       ← timer Pomodoro
cancela o timer
status do timer
mostra o tempo de uso
relatório de produtividade
relatório diário
```

### Perfis dinâmicos
```
perfil trabalho / perfil work
perfil casual
perfil foco / perfil focus
perfil reunião / perfil meeting
perfil noturno / perfil noite
qual perfil
lista perfis
```

### Google Calendar
```
o que tenho hoje / agenda hoje
próximo evento / próximo compromisso
adiciona reunião amanhã às 14h
adiciona dentista hoje às 10h30
autoriza calendário                   ← re-autoriza OAuth se necessário
```

### Lembretes
```
me lembra às 15h de reunião
me lembra em 30 minutos de fazer backup
lista lembretes
cancela lembrete 2
cancela lembretes
```

### Clipboard
```
copia o último resultado
copia Python é incrível para o clipboard
lê a área de transferência
limpa o clipboard
```

### OCR / Tela
```
lê o texto na tela
lê a região central
salva screenshot
```

### Contexto e sessão
```
mostra o contexto
limpa o contexto
resume a sessão
resume a reunião
```

### Dashboard web
```
abre o dashboard
inicia a interface web
para o servidor web / fecha o dashboard
```

### Obsidian
```
exporta a transcrição para o obsidian
exporta o sumário para o obsidian
cria a nota diária
exporta as notas para o obsidian
```

### Comandos encadeados
```
abre o VS Code e depois foco por 25 min
começa a transcrever e então ativa o detector de reunião
para a transcrição e em seguida exporta o sumário para o obsidian
```

### Plugins e meta
```
lista plugins
recarrega plugins
ajuda
```

---

## Configuração

Edite `core/config.yaml` (gerado automaticamente no primeiro boot do `Pacoca.exe`, ou configurado pelo wizard):

```yaml
# Wake word (deixe vazio para desabilitar e usar push-to-talk)
wake_word:
  enabled: true
  sensitivity: 0.5
  model_path: ""          # Caminho para modelo .onnx customizado (ex: pacoca.onnx)
                          # Para treinar "Paçoca": github.com/dscripka/openWakeWord#training

# IA local
ai:
  provider: ollama        # ollama | anthropic
  model: llama3           # llama3 | mistral | phi3

# Overlay
overlay:
  enabled: true
  position: top-right     # top-left | top-right | bottom-left | bottom-right

# TTS
tts:
  enabled: true
  engine: pyttsx3

# Dashboard web
web:
  password: ""            # deixe vazio para sem autenticação
```

### Anthropic como fallback (opcional)

```bash
set ANTHROPIC_API_KEY=sk-ant-...      # Windows
export ANTHROPIC_API_KEY=sk-ant-...   # Linux/Mac
```

Em `config.yaml`: `ai.provider: anthropic`

### Google Calendar e Drive (opcional)

O wizard (`Pacoca-Setup.exe`) faz o login automaticamente. Para configurar manualmente:

1. Crie um projeto em [Google Cloud Console](https://console.cloud.google.com)
2. Ative **Calendar API** e **Drive API**
3. Crie credenciais OAuth 2.0 (Aplicativo desktop) e baixe `credentials.json`
4. Coloque em `core/credentials.json`
5. Diga `"autoriza calendário"` — o browser abre para login

O token é salvo em `core/google_token.json` (cobre Calendar + Drive) e renovado automaticamente.

```yaml
calendar:
  credentials_path: core/credentials.json
  token_path: core/google_token.json
  timezone: America/Sao_Paulo

backup:
  google_drive:
    enabled: false
    credentials_path: core/credentials.json
    token_path: core/google_token.json
```

### Obsidian (opcional)

```yaml
obsidian:
  vault_path: C:/Users/seu_usuario/Documents/ObsidianVault/Paçoca
```

### Plugins

Coloque qualquer arquivo `.py` em `plugins/` e ele será carregado automaticamente no próximo boot (ou via `"recarrega plugins"`). Cada plugin deve declarar `NAME`, `VERSION`, `DESCRIPTION` e `ROUTES`. Use `plugins/_template.py` como ponto de partida.

---

## Estrutura do projeto

```
Pacoca/
├── main.py                    # entry point — argparse, boot, bootstrap PyInstaller
├── setup_wizard.py            # assistente de instalação GUI (tkinter, sem deps)
├── setup.bat / setup.sh       # instalação via código-fonte
├── pacoca.spec                # PyInstaller — build do Pacoca.exe (todas as deps bundled)
├── wizard.spec                # PyInstaller — build do Pacoca-Setup.exe
├── build.bat / build.sh       # scripts de build
├── requirements.txt
│
├── core/
│   ├── orchestrator.py        # roteador regex → módulos + plugins + dispatch_chain
│   ├── plugin_loader.py       # escaneia plugins/ e injeta rotas
│   ├── config.py              # carregador YAML com notação de pontos
│   ├── config.yaml            # configuração central
│   ├── profiles.py            # perfis work / casual / focus / meeting / night
│   └── logger.py              # logging rotativo em arquivo
│
├── input/
│   ├── stt.py                 # Whisper + wake word / push-to-talk + calibração
│   ├── hotkeys.py             # atalhos globais
│   └── cli.py                 # interface de terminal
│
├── modules/
│   ├── system_control.py      # apps, volume, brilho, processos
│   ├── transcription.py       # mic + loopback, auto-save
│   ├── summarizer.py          # Ollama + fallback Anthropic
│   ├── search.py              # roteamento IA local vs DuckDuckGo
│   ├── dev_tools.py           # VS Code, Git, arquivos, testes
│   ├── routines.py            # rotinas YAML com condições
│   ├── productivity.py        # monitoramento, Pomodoro, relatórios
│   ├── security.py            # confirmação de ações críticas
│   ├── backup.py              # backup local + Google Drive
│   ├── calendar_integration.py# Google Calendar — agenda, próximo evento, criar evento
│   ├── reminders.py           # lembretes agendados por voz
│   ├── clipboard_tools.py     # copiar/ler área de transferência por voz
│   ├── screen_reader.py       # OCR de tela via pytesseract
│   ├── meeting_detector.py    # detecta videochamadas via psutil
│   ├── obsidian.py            # exporta notas/transcrições para vault Markdown
│   └── web_server.py          # inicia o servidor do dashboard
│
├── output/
│   ├── tts.py                 # pyttsx3
│   ├── overlay.py             # overlay PyQt6 thread-safe
│   └── notifier.py            # notificações desktop
│
├── storage/
│   ├── db.py                  # SQLite — histórico e sessões
│   ├── file_store.py          # transcrições e resumos em Markdown
│   └── context.py             # memória contextual de sessão (ring buffer)
│
├── web/
│   ├── __init__.py
│   └── app.py                 # FastAPI + htmx + WebSocket — dashboard local
│
├── plugins/
│   ├── notes.py               # anotações rápidas (plugin incluso)
│   └── _template.py           # template para novos plugins
│
├── hooks/                     # runtime hooks do PyInstaller
│
└── tests/                     # 73 testes (pytest)
    ├── test_config.py
    ├── test_db.py
    ├── test_orchestrator.py
    ├── test_dispatch_chain.py
    ├── test_reminders.py
    └── test_context.py
```

---

## Stack tecnológica

| Funcionalidade | Ferramenta | Tipo |
|---|---|---|
| Speech-to-Text | faster-whisper (Whisper base) | Local / offline |
| Wake word | openWakeWord (sem API key) | Local / offline |
| LLM | Ollama (llama3 / mistral / phi3) | Local / offline |
| LLM cloud | Anthropic API (claude-haiku) | Opcional / pago |
| TTS | pyttsx3 | Local / offline |
| Busca web | duckduckgo-search | Gratuito |
| Overlay | PyQt6 | Open-source |
| Monitoramento | psutil | Open-source |
| Banco de dados | SQLite | Open-source |
| Backup nuvem | Google Drive API | Gratuito |
| Google Calendar | Google Calendar API (OAuth 2.0) | Gratuito |
| Dashboard web | FastAPI + htmx + uvicorn + WebSocket | Open-source |
| Config | PyYAML | Open-source |
| Empacotamento | PyInstaller | Open-source |

---

## Testes

```bash
python -m pytest tests/ -v
```

73 testes cobrindo: config, orchestrator (roteamento), banco de dados, STT, dev tools, dispatch_chain, lembretes e memória contextual.

CI automático via GitHub Actions em cada push para `main` e `dev`.

---

## Roadmap

### v0.1 — Concluído
- [x] Boot completo com logger, db e produtividade
- [x] Modo texto e modo voz (push-to-talk)
- [x] Overlay flutuante com estado e histórico
- [x] Transcrição mic + loopback + auto-save
- [x] Dev tools: git por voz, abrir arquivo, explicar código
- [x] Pomodoro, relatório diário, rotinas com condições
- [x] CI/CD com GitHub Actions

### v0.2 — Concluído
- [x] Calibração automática de ruído para o microfone
- [x] Integração com Google Calendar
- [x] Perfis dinâmicos por voz (work / casual / focus / meeting / night)
- [x] Plugin system — carregamento dinâmico e hot-reload por voz
- [x] Speaker diarization (`pyannote.audio`) — opcional, requer HF_TOKEN

### v0.3 — Concluído
- [x] Memória contextual — histórico da sessão injetado no prompt do LLM
- [x] Lembretes por voz — horário absoluto e relativo
- [x] Clipboard por voz
- [x] OCR de tela via pytesseract + Pillow
- [x] Troca de idioma STT por voz
- [x] Sumário de reunião estruturado + sumário de sessão

### v0.4 — Concluído
- [x] Dashboard web local (FastAPI + htmx) em localhost:7755
- [x] Exportação para Obsidian
- [x] Comandos encadeados naturais
- [x] Modo reunião automático (detecta Zoom/Teams/Slack via psutil)
- [x] TTS profile-aware
- [x] Flag `--web`

### v0.5 — Concluído
- [x] 73 testes — dispatch_chain, reminders e context
- [x] Dashboard WebSocket — resposta instantânea + push de eventos em tempo real
- [x] Editor visual de rotinas no dashboard (htmx CRUD)
- [x] Autenticação no dashboard — cookie + login (`web.password`)
- [x] **Pacoca.exe standalone** — todas as deps Python bundled via PyInstaller; zero pip install para o usuário final
- [x] **Setup wizard GUI** (`Pacoca-Setup.exe`) — instala Ollama, faz login Google, cria atalho; roda em qualquer PC Windows sem Python instalado
- [x] Token Google unificado (`google_token.json`) — cobre Calendar + Drive em um único OAuth

### v0.6 — Próximo
- [ ] Síntese de voz neural — vozes PT-BR mais naturais
- [ ] Streaming de resposta do LLM — tokens em tempo real no dashboard
- [ ] Testes para `web/app.py` (endpoints, WebSocket, CRUD de rotinas)

---

## Contribuição

1. Fork o repositório
2. Crie um módulo em `modules/` seguindo o padrão: funções públicas retornam `str`, use lazy imports
3. Registre as rotas em `core/orchestrator.py`
4. Adicione testes em `tests/`
5. Abra um Pull Request para `dev`

---

## Licença

MIT License — veja [LICENSE](LICENSE)

---

## Autor

Desenvolvido por [Athy (AthirsonLamonato)](https://github.com/AthirsonLamonato)
