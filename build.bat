@echo off
chcp 65001 >nul
echo.
echo [Pacoca] Compilando executavel para Windows...
echo.

:: Instalar PyInstaller se necessario
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [1/3] Instalando PyInstaller...
    pip install pyinstaller
) else (
    echo [1/3] PyInstaller ja instalado.
)

:: Criar pasta hooks se nao existir
if not exist "hooks" mkdir hooks

:: Compilar
echo.
echo [2/3] Compilando (pode levar alguns minutos)...
pyinstaller pacoca.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERRO] Falha na compilacao. Verifique as mensagens acima.
    pause
    exit /b 1
)

:: Copiar arquivos de dados necessarios em runtime
echo.
echo [3/3] Copiando arquivos de dados...
if not exist "dist\Pacoca\data" mkdir dist\Pacoca\data
if not exist "dist\Pacoca\logs" mkdir dist\Pacoca\logs

echo.
echo ════════════════════════════════════════════
echo  Build concluido!
echo  Executavel: dist\Pacoca\Pacoca.exe
echo.
echo  Para distribuir: copie toda a pasta dist\Pacoca\
echo  (o .exe sozinho nao funciona sem as DLLs ao lado)
echo ════════════════════════════════════════════
pause
