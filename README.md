# Axiom

> Seu assistente pessoal inteligente para automação, produtividade e desenvolvimento.

![Version](https://img.shields.io/badge/version-v0.1.0--alpha-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-red)

Assistente pessoal estilo Jarvis — automação, produtividade e IA rodando localmente.

---

# 📖 Visão geral

Axiom é um assistente de desktop modular, acionado por voz ou texto, construído inteiramente com ferramentas open-source e gratuitas.

O objetivo do projeto é criar uma IA pessoal capaz de:

- Controlar o computador por voz
- Automatizar tarefas repetitivas
- Auxiliar no desenvolvimento de software
- Transcrever reuniões
- Gerar resumos automáticos
- Integrar múltiplas inteligências artificiais
- Melhorar produtividade
- Servir como uma central pessoal inteligente

O projeto será desenvolvido inicialmente utilizando apenas ferramentas gratuitas e open-source.

---

# 🚀 Principais características

- Funciona 100% offline para funções essenciais
- Arquitetura modular
- IA local via Ollama
- Wake word personalizada (“Axiom”)
- Integração com VS Code, Git e terminal
- Dashboard flutuante
- Sistema de automação inteligente

---

# 🧩 Módulos e funcionalidades

| # | Módulo | Funcionalidade | Stack principal |
|---|---|---|---|
| 01 | Controle do sistema | Abrir/fechar apps, volume, brilho | pyautogui · psutil |
| 02 | STT + Wake word | Escuta contínua e ativação por voz | faster-whisper · pvporcupine |
| 03 | Transcrição | Captura mic + loopback | pyaudio · faster-whisper |
| 04 | Resumo inteligente | Resumo automático | Ollama |
| 05 | Pesquisa inteligente | IA local + internet | DuckDuckGo · Ollama |
| 06 | Dev Tools | VS Code, Git e shell | subprocess |
| 07 | Segurança | Confirmações e permissões | whitelist |
| 08 | TTS | Feedback de voz | pyttsx3 |
| 09 | Overlay visual | Dashboard flutuante | PyQt6 |
| 10 | Backup automático | Local + nuvem | Google Drive API |
| 11 | Modo foco | Escuta inteligente | pvporcupine |
| 12 | Perfis | Trabalho e casual | YAML |
| 13 | Produtividade | Monitoramento de apps | psutil |

---

# 🗂️ Estrutura do projeto

```text
axiom/
├── core/
│   ├── orchestrator.py
│   ├── config.yaml
│   └── profiles.py
│
├── input/
│   ├── stt.py
│   ├── hotkeys.py
│   └── cli.py
│
├── modules/
│   ├── system_control.py
│   ├── transcription.py
│   ├── summarizer.py
│   ├── search.py
│   ├── dev_tools.py
│   ├── routines.py
│   ├── productivity.py
│   ├── security.py
│   └── backup.py
│
├── output/
│   ├── tts.py
│   ├── overlay.py
│   └── notifier.py
│
├── storage/
│   ├── db.py
│   └── file_store.py
│
└── main.py
```

---

# ⚙️ Instalação

## 1. Pré-requisitos

- Python 3.10+
- Ollama instalado
- PortAudio

---

## 2. Clonar projeto

```bash
git clone https://github.com/seu-usuario/axiom.git
cd axiom
```

---

## 3. Criar ambiente virtual

### Linux/Mac

```bash
python -m venv .venv
source .venv/bin/activate
```

### Windows

```bash
.venv\Scripts\activate
```

---

## 4. Instalar dependências

```bash
pip install -r requirements.txt
```

---

## 5. Baixar IA local

```bash
ollama pull llama3
```

Alternativas:

```bash
ollama pull mistral
ollama pull phi3
```

---

## 6. Executar

```bash
python main.py
```

Modo texto:

```bash
python main.py --mode text
```

---

# 🧠 Stack tecnológica

| Funcionalidade | Ferramenta | Tipo |
|---|---|---|
| Speech-to-Text | faster-whisper | Local |
| Wake word | Porcupine | Local |
| IA local | Ollama | Local |
| TTS | pyttsx3 | Local |
| Busca web | DuckDuckGo | Gratuito |
| Overlay | PyQt6 | Open-source |
| Backup | Google Drive API | Gratuito |
| Monitoramento | ActivityWatch | Open-source |

---

# 📦 requirements.txt

```txt
faster-whisper
pyaudio
pvporcupine
keyboard
pynput
pyautogui
psutil
pyttsx3
PyQt6
schedule
requests
duckduckgo-search
plyer
pyyaml
google-auth
google-auth-oauthlib
google-api-python-client
```

---

# 🎙️ Exemplos de comandos

## Sistema

- “Axiom, abre o VS Code”
- “Axiom, fecha o Spotify”
- “Axiom, volume 60”
- “Axiom, aumenta o brilho”

---

## Transcrição

- “Axiom, começa a transcrever a reunião”
- “Axiom, para a transcrição”
- “Axiom, resume o que foi falado”

---

## Desenvolvimento

- “Axiom, cria um arquivo utils.py”
- “Axiom, faz commit”
- “Axiom, roda os testes”
- “Axiom, explica esse código”

---

## Pesquisa

- “Axiom, pesquisa como funciona recursão”
- “Axiom, busca na internet o clima de amanhã”

---

## Rotinas

- “Axiom, modo trabalho”
- “Axiom, modo foco”
- “Axiom, fim do dia”

---

# 🛣️ Roadmap

## Fase 1

- [ ] Núcleo do sistema
- [ ] IA local via Ollama
- [ ] Comandos básicos

## Fase 2

- [ ] Speech-to-Text
- [ ] Controle do sistema
- [ ] Text-to-Speech

## Fase 3

- [ ] Wake word
- [ ] Overlay visual
- [ ] Perfis inteligentes

## Fase 4

- [ ] Transcrição de reuniões
- [ ] Resumos automáticos
- [ ] Histórico inteligente

## Fase 5

- [ ] Integração avançada VS Code
- [ ] Git e automação dev
- [ ] Pesquisa inteligente

## Fase 6

- [ ] Rotinas inteligentes
- [ ] Backup automático
- [ ] Monitoramento de produtividade

---

# 🤝 Contribuição

Contribuições são bem-vindas.

Para adicionar um novo módulo:

1. Crie o módulo em `modules/`
2. Registre no `orchestrator.py`
3. Documente os comandos
4. Abra um Pull Request

---

# ⚡ Filosofia do projeto

O Axiom não é apenas um assistente virtual.

A ideia é criar uma central inteligente capaz de:

- Entender contexto
- Automatizar tarefas
- Auxiliar programação
- Organizar informações
- Evoluir constantemente

Tudo isso de forma modular, expansível e gratuita.

---

# 📄 Licença

MIT License

---

# 👨‍💻 Autor

Desenvolvido por Athy.