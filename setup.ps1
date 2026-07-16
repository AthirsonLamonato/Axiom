param(
    [ValidateSet("minimal", "full", "voice")]
    [string]$Mode = "",
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Set-Location -LiteralPath $ProjectRoot

function Find-Python {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike "*WindowsApps*") {
        return $command.Source
    }
    throw "Python 3.10+ nao encontrado. Instale Python 3.12 e execute novamente."
}

function Find-Ollama {
    $command = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $localOllama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $localOllama) { return $localOllama }
    return $null
}

if (-not $Mode) {
    Write-Host ""
    Write-Host "Pacoca - instalacao isolada" -ForegroundColor Cyan
    Write-Host "  1. minimal - texto sem voz/interface"
    Write-Host "  2. full    - texto, TTS, overlay e dashboard"
    Write-Host "  3. voice   - experiencia Jarvis completa" -ForegroundColor Yellow
    $choice = Read-Host "Escolha [1-3, padrao=3]"
    switch ($choice) {
        "1" { $Mode = "minimal" }
        "2" { $Mode = "full" }
        default { $Mode = "voice" }
    }
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $BasePython = Find-Python
    Write-Host "Criando ambiente virtual com $BasePython..." -ForegroundColor Cyan
    & $BasePython -m venv $VenvDir
}

Write-Host "Atualizando instalador de pacotes..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip

switch ($Mode) {
    "minimal" {
        & $VenvPython -m pip install -r requirements-minimal.txt
    }
    "full" {
        & $VenvPython -m pip install -r requirements.txt
    }
    "voice" {
        & $VenvPython -m pip install -r requirements.txt
        & $VenvPython -m pip install -r requirements-voice.txt
        Write-Host "Baixando o modelo local de ativacao Hey Jarvis..." -ForegroundColor Cyan
        & $VenvPython -c "from openwakeword.utils import download_models; download_models(['hey_jarvis'])"
        if ($LASTEXITCODE -ne 0) {
            throw "Nao foi possivel baixar o modelo Hey Jarvis. Verifique a conexao e tente novamente."
        }
    }
}

if ($Dev) {
    & $VenvPython -m pip install -r requirements-dev.txt
}

$Ollama = Find-Ollama
if ($Ollama) {
    Write-Host "Verificando o modelo de IA local llama3..." -ForegroundColor Cyan
    & $Ollama pull llama3
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "O Ollama foi encontrado, mas o modelo llama3 nao pode ser preparado."
    }
} else {
    Write-Warning "Ollama nao encontrado. Instale em https://ollama.com/download/windows e execute setup.bat novamente."
}

@(
    "data",
    "data\transcriptions",
    "data\backups",
    "data\screenshots",
    "logs"
) | ForEach-Object {
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot $_) | Out-Null
}

Write-Host "Validando codigo e dependencias..." -ForegroundColor Cyan
& $VenvPython -m compileall -q core input modules output plugins storage web main.py setup_wizard.py

$DoctorArgs = @("main.py", "--doctor", "--mode", "text", "--no-overlay")
if ($Mode -eq "minimal") {
    $DoctorArgs += "--no-tts"
}
if ($Mode -eq "voice") {
    $DoctorArgs = @("main.py", "--doctor", "--mode", "voice", "--web")
}
& $VenvPython @DoctorArgs
$DoctorExit = $LASTEXITCODE

Write-Host ""
if ($DoctorExit -eq 0) {
    Write-Host "Pacoca instalado e pronto." -ForegroundColor Green
    Write-Host "Execute run.bat e escolha o modo desejado."
} else {
    Write-Host "Instalacao concluida, mas o diagnostico encontrou pendencias acima." -ForegroundColor Yellow
}
exit $DoctorExit
