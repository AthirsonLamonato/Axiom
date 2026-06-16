# Referência de Comandos

> 120+ comandos disponíveis (regex direto, sem contar variações por NLU). Fale ou digite
> qualquer variação — o Paçoca entende linguagem natural.
> `⚠` = pede confirmação antes de executar.

---

## 🎵 Spotify

| Exemplo de comando | Ação |
|---|---|
| `autoriza o spotify` | Iniciar fluxo OAuth do Spotify |
| `toca a playlist Lo-fi` | Tocar playlist pelo nome |
| `toca a música Bohemian Rhapsody` | Buscar e tocar música |
| `toca o artista Pink Floyd no spotify` | Tocar artista |
| `toca Daft Punk` | Tocar qualquer coisa (música, álbum, artista) |
| `play Jazz` | Alternativa em inglês |
| `pausa a música` / `para a música` / `silencia a música` | Pausar |
| `retoma a música` / `continua` / `play` | Retomar |
| `próxima música` / `próxima faixa` | Avançar faixa |
| `música anterior` / `volta faixa` | Voltar faixa |
| `o que está tocando` / `toca agora` | Ver faixa atual |
| `que música é essa` | Ver faixa atual |

---

## 💻 Dev Tools & Git

| Exemplo de comando | Ação |
|---|---|
| `abre o VS Code` / `abre o editor` | Abrir VS Code |
| `abre o arquivo main.py` | Abrir arquivo no editor padrão |
| `vai para a linha 42` | Ir para linha no VS Code |
| `novo terminal` | Abrir terminal |
| `cria arquivo utils.py` | Criar arquivo vazio |
| `explica o arquivo orchestrator.py` | Explicar arquivo via IA |
| `commit "mensagem do commit"` | `git commit -m` ⚠ |
| `git push` | `git push` ⚠ |
| `git pull` | `git pull` |
| `o que mudou` / `git status` | `git status --short` |
| `mostra os últimos commits` / `git log` | `git log --oneline` |
| `cria branch feature/nova-funcao` | `git checkout -b` |
| `branch atual` | Branch ativa no momento |
| `roda os testes` / `executa os testes` | `pytest tests/ -v` |
| `formata o código` | Roda `black .` + `isort .` (requer `pip install black isort`) |

---

## ⚙️ Controle do Sistema

| Exemplo de comando | Ação |
|---|---|
| `abre o chrome` / `abre o spotify` | Abrir aplicativo |
| `fecha o chrome` | Fechar aplicativo ⚠ |
| `abre a pasta Downloads` | Abrir pasta no gerenciador de arquivos |
| `abre o explorador` | Abrir gerenciador de arquivos |
| `abre https://github.com` | Abrir URL no navegador |
| `abre o chrome no github.com` | Abrir URL em navegador específico |
| `pesquisa Python tutorial` | Busca no navegador padrão |
| `busca Python tutorial` | Busca no navegador padrão |
| `volume 70` | Definir volume em % |
| `aumenta o brilho` / `diminui o brilho` | Ajustar brilho |
| `muta o som` / `silencia o áudio` | Mutar/desmutar |
| `lista processos` / `mostra processos` | Listar processos ativos |

---

## 🎙️ Transcrição de Reuniões

| Exemplo de comando | Ação |
|---|---|
| `começa a transcrição` / `inicia transcrição` | Iniciar transcrição (microfone) |
| `começa a transcrição do sistema` | Iniciar loopback (áudio do sistema) |
| `para a transcrição` | Parar transcrição |
| `mostra o que foi falado` / `mostra a transcrição` | Exibir última transcrição |
| `identifica os falantes` / `diariza os falantes` | Speaker diarization (requer pyannote) |

---

## 📝 Resumos & IA

| Exemplo de comando | Ação |
|---|---|
| `resume o que foi falado` | Resumir última transcrição |
| `resume a reunião` | Resumir reunião atual |
| `resume a sessão` | Resumir sessão inteira |
| `resumo detalhado` | Resumo mais longo e detalhado |
| `explica recursão` / `o que é Docker` | Perguntar qualquer coisa para a IA |
| `busca por IA machine learning` | Busca com resumo por IA |

---

## 📊 Produtividade & Timer Pomodoro

| Exemplo de comando | Ação |
|---|---|
| `foco por 25 min` | Iniciar timer de foco (Pomodoro) |
| `foco por 2h` | Timer de 2 horas |
| `cancela o timer` / `para o timer` | Cancelar timer ativo |
| `status do timer` / `quanto tempo do timer` | Ver tempo restante |
| `mostra o tempo de uso` | Tempo por aplicativo (psutil) |
| `relatório de produtividade` | Resumo de produtividade |
| `relatório diário` | Relatório do dia atual |

---

## 📅 Calendário (Google Calendar)

| Exemplo de comando | Ação |
|---|---|
| `o que tenho hoje` / `agenda hoje` | Listar eventos de hoje |
| `agenda amanhã` | Listar eventos de amanhã |
| `próximo evento` / `próximo compromisso` | Próximo evento no calendário |
| `cria evento reunião amanhã às 14h` | Criar evento com linguagem natural |
| `adiciona no calendário dentista hoje às 10h` | Criar evento |
| `reunião amanhã às 14h com fulano@email.com` | Criar evento convidando e-mails mencionados na frase |
| `apaga o evento [título]` / `cancela o evento [título]` | Apaga por título (busca por trecho — só apaga se achar exatamente 1 correspondência) ⚠ |
| `autoriza o calendário` | Iniciar autenticação Google |

Remarcar/renomear um evento (`muda a reunião X pra amanhã às 16h`) e listar
agenda de qualquer dia específico não têm rota de voz direta — caem
automaticamente no raciocínio do LLM (`update_calendar_event`,
`get_calendar_events`), que entende linguagem livre melhor do que uma regex
conseguiria.

---

## ⏰ Lembretes

| Exemplo de comando | Ação |
|---|---|
| `me lembra de ligar às 15h` | Criar lembrete com horário |
| `me lembra tomar remédio em 30 minutos` | Lembrete relativo |
| `lista os lembretes` / `mostra os lembretes` | Ver lembretes pendentes |
| `cancela o lembrete 1` | Cancelar lembrete por número |

---

## 🔄 Rotinas

| Exemplo de comando | Ação |
|---|---|
| `modo trabalho` | Executar rotina `work_mode` do config.yaml |
| `modo foco` | Executar rotina `focus_mode` |
| `fim do dia` | Executar rotina `end_of_day` |
| `executa rotina minha_rotina` | Executar rotina pelo nome |

---

## 👤 Perfis

| Exemplo de comando | Ação |
|---|---|
| `ativa perfil work` | Mudar para perfil de trabalho |
| `perfil casual` / `perfil foco` / `perfil reunião` / `perfil noite` | Trocar perfil |
| `qual o perfil atual` / `mostra o perfil` | Ver perfil ativo |
| `lista os perfis` | Ver todos os perfis disponíveis |

---

## 🎤 STT & Idioma

| Exemplo de comando | Ação |
|---|---|
| `calibra o microfone` / `recalibra o mic` | Recalibrar limiar de ruído |
| `muda para inglês` / `troca para espanhol` | Trocar idioma do STT em tempo real |
| `idioma atual` | Ver idioma de reconhecimento ativo |

---

## 🧠 Memória & Aprendizado

| Exemplo de comando | Ação |
|---|---|
| `lembra que eu prefiro Python` | Salvar fato na knowledge base |
| `esquece que eu prefiro Python` | Remover fato |
| `o que você sabe sobre mim` | Ver dados salvos |
| `mostra as memórias` | Ver knowledge base |
| `mostra as preferências` | Ver preferências salvas |
| `aprende que deploy significa subir para produção` | Ensinar vocabulário personalizado |
| `o que você aprendeu` / `relatório de aprendizado` | Resumo de aprendizados |

---

## 📡 Detector de Reunião

| Exemplo de comando | Ação |
|---|---|
| `ativa o detector de reunião` | Monitorar silêncio e iniciar transcrição automaticamente |
| `desativa o detector de reunião` | Parar monitoramento |
| `status do detector` | Ver se está monitorando |

---

## 📓 Obsidian

| Exemplo de comando | Ação |
|---|---|
| `exporta a transcrição para o Obsidian` | Exportar para vault configurado |
| `exporta o sumário para o Obsidian` | Exportar resumo da reunião |
| `cria a nota diária` / `atualiza a nota diária` | Criar/atualizar nota com comandos do dia |
| `exporta as notas para o Obsidian` | Exportar anotações rápidas |

---

## 📋 Clipboard

| Exemplo de comando | Ação |
|---|---|
| `copia o último resultado` | Copiar última resposta do assistente |
| `copia texto para o clipboard` | Copiar texto específico |
| `lê o clipboard` / `mostra o clipboard` | Ler conteúdo da área de transferência |
| `limpa o clipboard` | Limpar clipboard |

---

## 👁️ Leitura de Tela

| Exemplo de comando | Ação |
|---|---|
| `lê o texto na tela` / `lê a tela` | OCR da tela (requer pytesseract) |
| `lê a região central` | OCR da região central da tela |
| `salva um screenshot` | Capturar e salvar screenshot |

---

## 🌤️ Clima

| Exemplo de comando | Ação |
|---|---|
| `como está o clima em São Paulo` | Previsão do tempo (Open-Meteo, sem API key) |
| `previsão do tempo em Curitiba` | Previsão para cidade |
| `como está o tempo` | Clima na cidade padrão do config |

---

## 💰 Finanças

| Exemplo de comando | Ação |
|---|---|
| `qual o valor do dólar` / `cotação do euro` | Cotação de moeda |
| `quanto está o Bitcoin hoje` | Cotação de cripto |
| `converte 100 dólares em reais` | Conversão de moeda |
| `50 euros em reais` | Conversão direta |

---

## 💾 Backup

| Exemplo de comando | Ação |
|---|---|
| `faz backup` / `executa backup` / `backup agora` | Backup local (e Drive se configurado) |

---

## 🌐 Dashboard Web

| Exemplo de comando | Ação |
|---|---|
| `abre o dashboard` / `inicia a interface web` | Iniciar em localhost:7755 |
| `fecha o dashboard` / `para o servidor web` | Parar servidor |

---

## 🪟 Janela de desktop

| Exemplo de comando | Ação |
|---|---|
| `abre o overlay` | Exibir a janela de desktop |
| `fecha o overlay` | Ocultar a janela de desktop |
| `ctrl+shift+a` | Mesma coisa, via atalho de teclado |

Quando `overlay.enabled: true` (padrão), essa janela tem histórico de
conversa, caixa de texto, botão de microfone (um comando de voz por clique)
e botão de conta Google — ver [configuracao.md](configuracao.md#overlay).

---

## 🔌 Plugins

| Exemplo de comando | Ação |
|---|---|
| `lista os plugins` / `mostra os plugins carregados` | Ver plugins ativos |
| `recarrega os plugins` / `reload os plugins` | Recarregar plugins da pasta `plugins/` |
| `anota comprar café` | Plugin de notas rápidas (`plugins/notes.py`) |
| `minhas anotações` / `últimas anotações` | Ver notas salvas |
| `busca nas anotações reunião` | Buscar em notas |

---

## 🔧 Sistema & Diagnóstico

| Exemplo de comando | Ação |
|---|---|
| `status das integrações` / `verifica as integrações` | Ver status de Groq, Ollama, Spotify, Calendar |
| `limpa os dados antigos` | Remover histórico mais velho que `privacy.retention_days` |
| `limpa o contexto` / `apaga o contexto` | Limpar histórico da sessão atual |
| `mostra o contexto` | Ver contexto da sessão atual |
| `ajuda` / `help` / `?` | Listar todos os comandos disponíveis |
