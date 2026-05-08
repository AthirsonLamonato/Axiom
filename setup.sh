#!/usr/bin/env bash
set -e

echo ""
echo " ██████╗ ██╗  ██╗██╗  ██████╗ ███╗   ███╗"
echo "██╔══██╗╚██╗██╔╝██║ ██╔═══██╗████╗ ████║"
echo "███████║ ╚███╔╝ ██║ ██║   ██║██╔████╔██║"
echo "██╔══██║ ██╔██╗ ██║ ██║   ██║██║╚██╔╝██║"
echo "██║  ██║██╔╝ ██╗██║ ╚██████╔╝██║ ╚═╝ ██║"
echo "╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═════╝ ╚═╝     ╚═╝"
echo ""
echo " Instalador do Axiom para Linux/Mac"
echo "════════════════════════════════════════════"
echo ""

# Verificar Python
if ! command -v python3 &>/dev/null; then
    echo "[ERRO] Python3 não encontrado. Instale Python 3.9+"
    exit 1
fi
PYVER=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "[OK] Python $PYVER encontrado."

# Instalar dependências
echo ""
echo "[1/5] Instalando dependências Python (requirements.txt)..."
pip3 install -r requirements.txt
echo "[OK] Dependências instaladas."

# Dashboard web
echo ""
echo "[2/5] Instalando dashboard web (FastAPI + uvicorn)..."
pip3 install fastapi "uvicorn[standard]"
echo "[OK] Dashboard web disponível."

# Criar diretórios
echo ""
echo "[3/5] Criando diretórios..."
mkdir -p data/transcriptions data/backups data/screenshots logs plugins
echo "[OK] Diretórios criados."

# Testes
echo ""
echo "[4/5] Verificando instalação (testes)..."
if python3 -m pytest tests/ -q --tb=no 2>/dev/null; then
    echo "[OK] Todos os testes passaram."
else
    echo "[AVISO] Alguns testes falharam. Execute 'python3 -m pytest tests/ -v' para detalhes."
fi

# Ollama
echo ""
echo "[5/5] Modelo de IA local (Ollama)..."
if ! command -v ollama &>/dev/null; then
    echo "[AVISO] Ollama não encontrado."
    echo "        Para usar IA local, instale via:"
    echo "        curl -fsSL https://ollama.com/install.sh | sh"
    echo "        Depois execute: ollama pull llama3"
else
    echo "Ollama encontrado. Baixando modelo llama3 (~4 GB)..."
    echo "(Pressione Ctrl+C para pular)"
    ollama pull llama3
    echo "[OK] Modelo llama3 pronto."
fi

echo ""
echo "════════════════════════════════════════════"
echo " Instalação concluída!"
echo ""
echo " Para iniciar:"
echo "   python3 main.py --mode text --no-tts     (teste sem microfone)"
echo "   python3 main.py --web                    (com dashboard web)"
echo "   python3 main.py                          (modo completo com voz)"
echo ""
