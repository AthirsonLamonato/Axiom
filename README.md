# Paçoca

> Assistente pessoal inteligente de desktop — controle por voz ou texto, 100% open-source e gratuito.

![Version](https://img.shields.io/badge/version-v0.6.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Tests](https://img.shields.io/badge/tests-222%20passing-brightgreen)
![CI](https://github.com/AthirsonLamonato/Pacoca/actions/workflows/tests.yml/badge.svg)

Paçoca é um assistente de desktop estilo Jarvis — modular, expansível e capaz de rodar completamente offline em hardware modesto (4 GB RAM, CPU sem GPU).

---

## Instalação

> Ainda não há um instalador `.exe` publicado nas releases do GitHub — os scripts
> `pacoca.spec`/`wizard.spec`/`setup_wizard.py` existem no repositório para build
> local, mas instale a partir do código-fonte por enquanto.

```bash
git clone https://github.com/AthirsonLamonato/Pacoca.git
cd Pacoca
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
| **STT** | Transcrição via Whisper (`faster-whisper`). Calibração automática de ruído; VAD por energia RMS. Push-to-talk `ctrl+shift+space` por padrão; wake word via openWakeWord (sem API key, modelo customizável) |
| **Overlay** | Janela flutuante PyQt6: estado (idle / listening / processing / speaking), histórico dos 3 últimos comandos, fade animado. Toggle: `ctrl+shift+a` |
| **Transcrição** | Captura microfone ou loopback do sistema (Windows: WASAPI · Linux: PulseAudio). Auto-save a cada 5 min |
| **Resumo / IA** | Resumo e explicações via Ollama (local) com fallback para Groq API (gratuito) |
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
| **TTS** | edge-tts (Microsoft Neural, padrão, requer internet) com fallback automático para pyttsx3 (100% offline) |

---

## Comandos disponíveis

> Lista completa e sempre atualizada em [docs/comandos.md](docs/comandos.md) ou no
> dashboard web em `/docs` (`python main.py --web`).

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

Edite `core/config.yaml` (já vem com valores padrão no repositório):

```yaml
# Wake word (deixe vazio para desabilitar e usar push-to-talk)
wake_word:
  enabled: true
  sensitivity: 0.5
  model_path: ""          # Caminho para modelo .onnx customizado (ex: pacoca.onnx)
                          # Para treinar "Paçoca": github.com/dscripka/openWakeWord#training

# IA local
ai:
  provider: ollama        # ollama | groq
  model: llama3           # llama3 | mistral | phi3

# Overlay
overlay:
  enabled: true
  position: top-right     # top-left | top-right | bottom-left | bottom-right

# TTS
tts:
  enabled: true
  engine: edge            # edge (online, voz neural) | pyttsx3 (offline) | coqui

# Dashboard web
web:
  password: ""            # deixe vazio para sem autenticação
```

### Groq como fallback (opcional, gratuito)

1. Crie conta gratuita em [console.groq.com](https://console.groq.com) e gere uma API key
2. Defina a variável de ambiente:

```bash
set GROQ_API_KEY=gsk_...      # Windows
export GROQ_API_KEY=gsk_...   # Linux/Mac
```

3. Em `config.yaml`: `ai.provider: groq`

O plano gratuito da Groq oferece 30 requisições/minuto e 6.000 tokens/minuto — mais que suficiente para uso pessoal.

### Google Calendar e Drive (opcional)

Configuração manual (ainda não há instalador que automatize este passo):

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
│   ├── summarizer.py          # Ollama + fallback Groq (gratuito)
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
│   ├── tts.py                 # edge-tts (padrão) com fallback pyttsx3/Coqui
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
└── tests/                     # 222 testes (pytest)
    ├── test_config.py
    ├── test_db.py
    ├── test_orchestrator.py
    ├── test_dispatch_chain.py
    ├── test_reminders.py
    ├── test_context.py
    ├── test_providers.py      # circuit breaker, cache TTL, retry
    ├── test_telemetry.py
    └── test_web_endpoints.py  # auth, CSRF, rate limit, sessão do dashboard
```

---

## Stack tecnológica

| Funcionalidade | Ferramenta | Tipo |
|---|---|---|
| Speech-to-Text | faster-whisper (Whisper base) | Local / offline |
| Wake word | openWakeWord (sem API key) | Local / offline |
| LLM | Ollama (llama3 / mistral / phi3) | Local / offline |
| LLM cloud | Groq API (llama3, free tier) | Opcional / gratuito |
| TTS | edge-tts (padrão, voz neural) com fallback para pyttsx3 | Gratuito / offline opcional |
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

222 testes (8 skipped — exigem rede/credenciais reais) cobrindo: config, orchestrator
(roteamento), banco de dados, STT, dev tools, dispatch_chain, lembretes, memória
contextual, providers (circuit breaker, cache, retry), telemetria e endpoints do
dashboard web (autenticação, CSRF, rate limit, sessão).

CI automático via GitHub Actions em cada push para `main`/`dev`, em matriz
Windows + Linux.

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

### v0.6 — Concluído
- [x] Substituição do Anthropic por **Groq** como fallback cloud (free tier, llama3)
- [x] `credentials.json` OAuth embutido diretamente no `Pacoca-Setup.exe` via PyInstaller
- [x] OAuth Google simplificado no wizard — fluxo unificado sem etapas manuais
- [x] Wizard baixa `Pacoca.exe` automaticamente se não encontrado na pasta
- [x] openWakeWord substituindo pvporcupine (sem API key, totalmente open-source)

### Não lançado (atual)
- [x] Arquitetura de providers centralizada (`core/providers.py`) — circuit breaker,
      retry exponencial, cache TTL, pool de conexões HTTP
- [x] Telemetria de comandos (`core/telemetry.py`) — exposta em `/metrics`
- [x] Síntese de voz neural — `edge-tts` como motor padrão (fallback automático para pyttsx3)
- [x] Testes para `web/app.py` (auth, CSRF, rate limit, sessão) e `core/providers.py`
- [x] Sessão do dashboard com cookie assinado (HMAC) em vez de hash estático da senha
- [x] CI em matriz Windows + Linux

### Próximo
- [ ] Streaming de resposta do LLM — tokens em tempo real no dashboard
- [ ] Treinar modelo de wake word "Paçoca" customizado (hoje usa `hey_jarvis`)
- [ ] Validar `pacoca.spec`/`wizard.spec` gerando um executável funcional e
      publicar a primeira release no GitHub (`pacoca.spec`/`wizard.spec` existem
      no repositório, mas **ainda não há nenhuma release publicada**)

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
