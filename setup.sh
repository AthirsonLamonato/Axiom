#!/usr/bin/env bash
set -e

echo "============================================"
echo " Axiom — Instalacao de dependencias"
echo "============================================"
echo

if ! command -v python3 &>/dev/null; then
    echo "[ERRO] Python3 nao encontrado. Instale Python 3.10+"
    exit 1
fi

echo "[1/4] Instalando dependencias principais..."
pip3 install pyyaml psutil requests duckduckgo-search schedule keyboard plyer
pip3 install faster-whisper pyaudio
pip3 install PyQt6 pyttsx3

echo
echo "[2/4] Instalando dependencias de desenvolvimento..."
pip3 install pytest

echo
echo "[3/4] Verificando Ollama..."
if ! command -v ollama &>/dev/null; then
    echo "[AVISO] Ollama nao encontrado."
    echo "        Instale via: curl -fsSL https://ollama.com/install.sh | sh"
    echo "        Depois execute: ollama pull llama3"
else
    echo "[OK] Ollama encontrado."
    echo "     Para baixar o modelo: ollama pull llama3"
fi

echo
echo "[4/4] Testando instalacao..."
if python3 -m pytest tests/ -q 2>/dev/null; then
    echo "[OK] Todos os testes passaram."
else
    echo "[AVISO] Alguns testes falharam. Verifique as dependencias."
fi

echo
echo "============================================"
echo " Instalacao concluida!"
echo " Execute: python3 main.py --mode text --no-tts --no-overlay"
echo "============================================"
