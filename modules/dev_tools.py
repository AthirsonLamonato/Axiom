"""
modules/dev_tools.py — Integração com ambiente de desenvolvimento
VS Code, Git, terminal e criação de arquivos por voz.
"""

import subprocess
import logging
import os
import platform

logger = logging.getLogger(__name__)
OS = platform.system()


# ── VS Code ────────────────────────────────────────────────────────────

def open_vscode(*_) -> str:
    """Abre o VS Code no diretório atual ou no workspace configurado."""
    try:
        subprocess.Popen("code .", shell=True)
        return "VS Code aberto."
    except Exception as e:
        return f"Erro ao abrir VS Code: {e}"


def open_terminal(*_) -> str:
    """Abre um terminal."""
    if OS == "Windows":
        subprocess.Popen("wt", shell=True)  # Windows Terminal
    elif OS == "Linux":
        for term in ("gnome-terminal", "xterm", "konsole"):
            try:
                subprocess.Popen(term)
                break
            except FileNotFoundError:
                continue
    elif OS == "Darwin":
        subprocess.Popen(["open", "-a", "Terminal"])
    return "Terminal aberto."


# ── Arquivos ───────────────────────────────────────────────────────────

def create_file(file_type: str, filename: str) -> str:
    """Cria um arquivo vazio com o nome especificado."""
    filename = filename.strip().strip("'\"")
    # Garante extensão para tipos comuns sem extensão explícita
    if "." not in filename:
        ext_map = {
            "arquivo": "",
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "html": ".html",
            "css": ".css",
            "json": ".json",
            "yaml": ".yaml",
            "markdown": ".md",
            "txt": ".txt",
        }
        for key, ext in ext_map.items():
            if key in file_type.lower():
                filename += ext
                break

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("")
        logger.info(f"Arquivo criado: {filename}")
        return f"Arquivo '{filename}' criado."
    except Exception as e:
        return f"Erro ao criar '{filename}': {e}"


# ── Git ────────────────────────────────────────────────────────────────

def git_commit(message: str) -> str:
    """Executa git add . && git commit -m 'message'."""
    message = message.strip().strip("'\"")
    try:
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return f"Commit realizado: '{message}'."
        return f"Erro no commit: {result.stderr.strip()}"
    except FileNotFoundError:
        return "Git não encontrado. Instale o Git."
    except subprocess.CalledProcessError as e:
        return f"Erro: {e.stderr}"


def git_push(*_) -> str:
    """Executa git push."""
    result = subprocess.run(
        ["git", "push"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return "Push realizado com sucesso."
    return f"Erro no push: {result.stderr.strip()}"


def git_pull(*_) -> str:
    """Executa git pull."""
    result = subprocess.run(
        ["git", "pull"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return "Pull realizado: " + result.stdout.strip()
    return f"Erro no pull: {result.stderr.strip()}"


def git_status(*_) -> str:
    result = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True
    )
    return result.stdout.strip() or "Repositório limpo."


# ── Testes ─────────────────────────────────────────────────────────────

def run_tests(*_) -> str:
    """Detecta e executa o runner de testes do projeto."""
    if os.path.exists("pytest.ini") or os.path.exists("pyproject.toml"):
        runner = ["python", "-m", "pytest", "-v", "--tb=short"]
    elif os.path.exists("package.json"):
        runner = ["npm", "test"]
    else:
        runner = ["python", "-m", "unittest", "discover"]

    try:
        result = subprocess.run(runner, capture_output=True, text=True, timeout=120)
        output = (result.stdout + result.stderr).strip()
        status = "Testes passaram." if result.returncode == 0 else "Falhas encontradas."
        # Retorna as últimas linhas para não sobrecarregar o TTS
        lines = output.split("\n")
        summary = "\n".join(lines[-8:])
        return f"{status}\n{summary}"
    except subprocess.TimeoutExpired:
        return "Timeout: testes demoraram mais de 2 minutos."
    except Exception as e:
        return f"Erro ao rodar testes: {e}"
