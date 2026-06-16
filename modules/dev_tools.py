"""
modules/dev_tools.py — Integração com ambiente de desenvolvimento
VS Code, Git, terminal, arquivos e explicação de código via IA.
"""

import subprocess
import logging
import os
import platform

logger = logging.getLogger(__name__)
OS = platform.system()


# ── VS Code ────────────────────────────────────────────────────────────

def open_vscode(*_) -> str:
    try:
        subprocess.Popen("code .", shell=True)
        return "VS Code aberto."
    except Exception as e:
        return f"Erro ao abrir VS Code: {e}"


def open_file(filename: str, *_) -> str:
    """Abre um arquivo no VS Code. Busca recursivamente se necessário."""
    filename = filename.strip().strip("'\"")
    path = _resolve_file(filename)
    if path is None:
        return f"Arquivo '{filename}' não encontrado."
    try:
        subprocess.Popen(["code", path], shell=True)
        return f"Abrindo {path} no VS Code."
    except Exception as e:
        return f"Erro ao abrir arquivo: {e}"


def goto_line(line: str, *_) -> str:
    """Vai para uma linha específica no arquivo aberto no VS Code."""
    line = line.strip()
    if not line.isdigit():
        return "Número de linha inválido."
    # Pega o arquivo mais recentemente modificado como alvo (heurística)
    try:
        result = subprocess.run(
            ["code", "--goto", f":{line}"], shell=True, capture_output=True
        )
        return f"Navegando para linha {line}."
    except Exception as e:
        return f"Erro ao navegar: {e}"


def open_terminal(*_) -> str:
    if OS == "Windows":
        subprocess.Popen("wt", shell=True)
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
    filename = filename.strip().strip("'\"")
    if "." not in filename:
        ext_map = {
            "python": ".py", "javascript": ".js", "typescript": ".ts",
            "html": ".html", "css": ".css", "json": ".json",
            "yaml": ".yaml", "markdown": ".md", "txt": ".txt",
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


def explain_file(filename: str, *_) -> str:
    """Lê um arquivo e pede ao LLM que explique o código."""
    filename = filename.strip().strip("'\"")
    path = _resolve_file(filename)
    if path is None:
        return f"Arquivo '{filename}' não encontrado."
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return f"Erro ao ler '{path}': {e}"

    if len(content) > 8000:
        content = content[:8000] + "\n... (truncado)"

    from modules.summarizer import ask_ai
    prompt = (
        f"Explique o seguinte código de forma clara e objetiva. "
        f"Arquivo: {os.path.basename(path)}\n\n```\n{content}\n```"
    )
    return ask_ai(prompt)


def _resolve_file(filename: str) -> "str | None":
    """Retorna o caminho completo do arquivo: direto ou buscando recursivamente."""
    if os.path.isfile(filename):
        return filename
    # Busca recursiva a partir do diretório atual (ignora .venv, __pycache__, .git)
    skip = {".venv", "venv", "__pycache__", ".git", "node_modules", ".cache"}
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            if f == filename or f == os.path.basename(filename):
                return os.path.join(root, f)
    return None


# ── Git ────────────────────────────────────────────────────────────────

def _git(*args) -> subprocess.CompletedProcess:
    """Executa um comando git com encoding UTF-8."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def git_commit(message: str) -> str:
    message = message.strip().strip("'\"")
    try:
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        result = _git("commit", "-m", message)
        if result.returncode == 0:
            return f"Commit realizado: '{message}'."
        return f"Erro no commit: {result.stderr.strip()}"
    except FileNotFoundError:
        return "Git não encontrado."
    except subprocess.CalledProcessError as e:
        return f"Erro: {e.stderr}"


def git_push(*_) -> str:
    result = _git("push")
    return "Push realizado." if result.returncode == 0 else f"Erro: {result.stderr.strip()}"


def git_pull(*_) -> str:
    result = _git("pull")
    if result.returncode == 0:
        return "Pull: " + result.stdout.strip()
    return f"Erro no pull: {result.stderr.strip()}"


def git_status(*_) -> str:
    result = _git("status", "--short")
    return result.stdout.strip() or "Repositório limpo, nenhuma alteração."


def git_log(*_) -> str:
    result = _git("log", "--oneline", "-5")
    if result.returncode != 0:
        return f"Erro: {result.stderr.strip()}"
    return result.stdout.strip() or "Nenhum commit encontrado."


def git_create_branch(branch_name: str, *_) -> str:
    branch_name = branch_name.strip().strip("'\"").replace(" ", "-")
    result = _git("checkout", "-b", branch_name)
    if result.returncode == 0:
        return f"Branch '{branch_name}' criada e ativada."
    return f"Erro ao criar branch: {result.stderr.strip()}"


def git_branch_current(*_) -> str:
    result = _git("branch", "--show-current")
    branch = result.stdout.strip()
    return f"Branch atual: {branch}" if branch else "Não está em um repositório Git."


# ── Testes ─────────────────────────────────────────────────────────────

def run_tests(*_) -> str:
    if (
        os.path.exists("pytest.ini")
        or os.path.exists("pyproject.toml")
        or os.path.isdir("tests")
    ):
        runner = [os.sys.executable, "-m", "pytest", "tests", "-v", "--tb=short"]
    elif os.path.exists("package.json"):
        runner = ["npm", "test"]
    else:
        runner = ["python", "-m", "unittest", "discover"]

    try:
        result = subprocess.run(runner, capture_output=True, text=True, timeout=120)
        output = (result.stdout + result.stderr).strip()
        status = "Testes passaram." if result.returncode == 0 else "Falhas encontradas."
        lines = output.split("\n")
        return f"{status}\n" + "\n".join(lines[-8:])
    except subprocess.TimeoutExpired:
        return "Timeout: testes demoraram mais de 2 minutos."
    except Exception as e:
        return f"Erro ao rodar testes: {e}"


def format_code(*_) -> str:
    """Formata o código do projeto com black + isort, se instalados."""
    results = []
    for tool in ("black", "isort"):
        try:
            result = subprocess.run(
                [os.sys.executable, "-m", tool, "."],
                capture_output=True, text=True, timeout=60,
            )
            output = (result.stdout + result.stderr).strip().splitlines()
            tail = "\n".join(output[-5:]) if output else "sem alterações"
            results.append(f"{tool}: {'ok' if result.returncode == 0 else 'erro'}\n{tail}")
        except FileNotFoundError:
            results.append(f"{tool}: não instalado (pip install {tool})")
        except subprocess.TimeoutExpired:
            results.append(f"{tool}: timeout (mais de 60s)")
        except Exception as e:
            results.append(f"{tool}: erro — {e}")
    return "\n\n".join(results)
