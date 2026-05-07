@echo off
echo ============================================
echo  Axiom — Instalacao de dependencias
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale Python 3.10+ em https://python.org
    pause
    exit /b 1
)

echo [1/4] Instalando dependencias principais...
pip install pyyaml psutil requests duckduckgo-search schedule keyboard plyer
pip install faster-whisper pyaudio
pip install PyQt6 pyttsx3

echo.
echo [2/4] Instalando dependencias de desenvolvimento...
pip install pytest

echo.
echo [3/4] Verificando Ollama...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Ollama nao encontrado.
    echo         Baixe em: https://ollama.com
    echo         Depois execute: ollama pull llama3
) else (
    echo [OK] Ollama encontrado.
    echo     Para baixar o modelo: ollama pull llama3
)

echo.
echo [4/4] Testando instalacao...
python -m pytest tests/ -q 2>nul
if errorlevel 1 (
    echo [AVISO] Alguns testes falharam. Verifique as dependencias.
) else (
    echo [OK] Todos os testes passaram.
)

echo.
echo ============================================
echo  Instalacao concluida!
echo  Execute: python main.py --mode text --no-tts --no-overlay
echo ============================================
pause
