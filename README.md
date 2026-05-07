# Axiom

> Assistente pessoal inteligente de desktop — controle por voz ou texto, 100% open-source e gratuito.

![Version](https://img.shields.io/badge/version-v0.1.0--alpha-blue)
![Python](https://img.shields.io/badge/python-3.9+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Tests](https://img.shields.io/badge/tests-36%20passing-brightgreen)
![CI](https://github.com/AthirsonLamonato/Axiom/actions/workflows/tests.yml/badge.svg)

Axiom é um assistente de desktop estilo Jarvis — modular, expansível e capaz de rodar completamente offline em hardware modesto (4 GB RAM, CPU sem GPU).

---

## Funcionalidades implementadas

| Módulo | O que faz |
|---|---|
| **STT** | Transcrição via Whisper (`faster-whisper`). Modo push-to-talk (ctrl+shift+space) por padrão; wake word via Porcupine se `access_key` configurada |
| **Overlay** | Janela flutuante PyQt6 sempre visível: indicador de estado (idle / listening / processing / speaking), histórico dos últimos 3 comandos, fade animado. Toggle: ctrl+shift+a |
| **Transcrição** | Captura microfone ou loopback do sistema (Windows: WASAPI · Linux: PulseAudio). Auto-save a cada 5 min |
| **Resumo / IA** | Resumo e explicações via Ollama (local) com fallback para Anthropic API |
| **Pesquisa** | Roteamento automático: perguntas factuais/atuais → DuckDuckGo + IA; demais → LLM local |
| **Dev tools** | VS Code, abrir arquivo por nome, ir para linha, criar arquivo, git status/log/commit/push/pull/branch, rodar testes, explicar código via IA |
| **Rotinas** | Sequências configuráveis em YAML com condições (weekday, weekend, morning, afternoon, evening) |
| **Pomodoro** | Timer de foco com notificação e overlay ao término |
| **Produtividade** | Monitoramento de apps via psutil, relatório diário em Markdown |
| **Sistema** | Abrir/fechar apps, volume, brilho, listar processos (Windows + Linux) |
| **Segurança** | Confirmação antes de ações críticas, lista configurável |
| **Backup** | Local automático + Google Drive (opcional, requer OAuth) |
| **Banco de dados** | SQLite — histórico de comandos, sessões e transcrições |
| **TTS** | pyttsx3 (offline, leve) ou Coqui TTS (mais natural) |

---

## Instalação rápida

### Windows

```bat
git clone https://github.com/AthirsonLamonato/Axiom.git
cd Axiom
setup.bat
```

### Linux / Mac

```bash
git clone https://github.com/AthirsonLamonato/Axiom.git
cd Axiom
bash setup.sh
```

### Manual

```bash
pip install -r requirements.txt
ollama pull llama3   # baixa o modelo de IA local (~4 GB)
```

---

## Executar

```bash
# Modo texto — ideal para testar sem microfone
python main.py --mode text --no-tts --no-overlay

# Modo texto com overlay
python main.py --mode text --no-tts

# Modo voz (push-to-talk por padrão)
python main.py

# Editor de rotinas
python main.py --edit-routines
```

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
novo terminal
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

### Overlay e meta
```
abre o overlay / fecha o overlay      ← ou ctrl+shift+a
ajuda                                 ← lista todos os comandos
```

---

## Configuração

Edite `core/config.yaml`:

```yaml
# Wake word (deixe vazio para push-to-talk)
wake_word:
  access_key: ""          # PICOVOICE_ACCESS_KEY — obtenha em picovoice.ai
  keyword: porcupine      # keywords gratuitas: porcupine, jarvis, computer…

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
  engine: pyttsx3         # pyttsx3 | coqui
```

### Anthropic como fallback (opcional)

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Linux/Mac
set ANTHROPIC_API_KEY=sk-ant-...      # Windows
```

Em `config.yaml`: `ai.provider: anthropic`

### Google Drive para backup (opcional)

1. Crie um projeto em [Google Cloud Console](https://console.cloud.google.com)
2. Ative a Drive API e baixe `credentials.json`
3. Coloque em `core/credentials.json`
4. Em `config.yaml`: `backup.google_drive.enabled: true`

---

## Estrutura do projeto

```
Axiom/
├── main.py                    # entry point — argparse, boot completo
├── setup.bat / setup.sh       # scripts de instalação
├── requirements.txt
│
├── core/
│   ├── orchestrator.py        # roteador regex → módulos
│   ├── config.py              # carregador YAML com notação de pontos
│   ├── config.yaml            # configuração central
│   ├── profiles.py            # perfis work / casual
│   └── logger.py              # logging rotativo em arquivo
│
├── input/
│   ├── stt.py                 # Whisper + wake word / push-to-talk
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
│   └── backup.py              # backup local + Google Drive
│
├── output/
│   ├── tts.py                 # pyttsx3 / Coqui TTS
│   ├── overlay.py             # overlay PyQt6 thread-safe
│   └── notifier.py            # notificações desktop
│
├── storage/
│   ├── db.py                  # SQLite — histórico e sessões
│   └── file_store.py          # transcrições e resumos em Markdown
│
└── tests/                     # 36 testes (pytest)
    ├── test_config.py
    ├── test_db.py
    ├── test_orchestrator.py
    ├── test_stt.py
    └── test_dev_tools.py
```

---

## Stack tecnológica

| Funcionalidade | Ferramenta | Tipo |
|---|---|---|
| Speech-to-Text | faster-whisper (Whisper base) | Local / offline |
| Wake word | pvporcupine (free tier) | Local / offline |
| LLM | Ollama (llama3 / mistral / phi3) | Local / offline |
| LLM cloud | Anthropic API (claude-haiku) | Opcional / pago |
| TTS | pyttsx3 / Coqui TTS | Local / offline |
| Busca web | duckduckgo-search | Gratuito |
| Overlay | PyQt6 | Open-source |
| Monitoramento | psutil | Open-source |
| Banco de dados | SQLite | Open-source |
| Backup nuvem | Google Drive API | Gratuito |
| Config | PyYAML | Open-source |

---

## Testes

```bash
python -m pytest tests/ -v
```

36 testes cobrindo: config, orchestrator (roteamento), banco de dados, STT e dev tools.

CI automático via GitHub Actions em cada push para `main` e `dev`.

---

## Roadmap

### v0.1 — Base (concluído)
- [x] Boot completo com logger, db e produtividade
- [x] Modo texto e modo voz (push-to-talk)
- [x] Overlay flutuante com estado e histórico
- [x] Transcrição mic + loopback + auto-save
- [x] Dev tools: git por voz, abrir arquivo, explicar código
- [x] Pomodoro, relatório diário, rotinas com condições
- [x] CI/CD com GitHub Actions

### v0.2 — Próximo
- [ ] Speaker diarization (`pyannote.audio`) — identificação de falantes
- [ ] Calibração automática de ruído para o microfone
- [ ] Integração com Google Calendar
- [ ] Modos de perfil dinâmicos via voz
- [ ] Plugin system para módulos externos

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
