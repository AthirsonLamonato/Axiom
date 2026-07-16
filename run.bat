@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo.
echo  Pacoca - Quick Start
echo ==================================
echo.
echo  Modos disponiveis:
echo    [1] Texto simples    (sem microfone, sem TTS)   - mais leve
echo    [2] Texto com TTS    (sem microfone, com voz)
echo    [3] Texto + Overlay  (sem microfone, com janela flutuante)
echo    [4] Voz completo     (microfone + TTS + overlay)
echo    [5] Com dashboard    (adiciona interface web em localhost:7755)
echo    [6] Diagnostico      (verifica se a experiencia Jarvis esta pronta)
echo.
set /p MODO="Escolha o modo [1-6, padrao=4]: "
if "%MODO%"=="" set MODO=4

"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Execute setup.bat primeiro.
    pause
    exit /b 1
)

if "%MODO%"=="1" (
    echo Iniciando modo texto simples...
    "%PYTHON%" main.py --mode text --no-tts --no-overlay
) else if "%MODO%"=="2" (
    echo Iniciando modo texto com TTS...
    "%PYTHON%" main.py --mode text --no-overlay
) else if "%MODO%"=="3" (
    echo Iniciando modo texto com overlay...
    "%PYTHON%" main.py --mode text --no-tts
) else if "%MODO%"=="4" (
    echo Iniciando modo voz completo...
    "%PYTHON%" main.py --mode voice
) else if "%MODO%"=="5" (
    echo Iniciando com dashboard web...
    "%PYTHON%" main.py --mode text --no-tts --web
) else if "%MODO%"=="6" (
    echo Verificando componentes...
    "%PYTHON%" main.py --doctor --mode voice --web
) else (
    echo [ERRO] Opcao invalida. Iniciando modo 4.
    "%PYTHON%" main.py --mode voice
)
pause
