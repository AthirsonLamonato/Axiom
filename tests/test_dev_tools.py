"""Testes para modules/dev_tools.py"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.dev_tools import (
    git_status, git_log, git_branch_current,
    create_file, _resolve_file, explain_file,
    git_create_branch, run_tests, format_code,
)


# ── Git ────────────────────────────────────────────────────────────────

def test_git_status_returns_string():
    result = git_status()
    assert isinstance(result, str)


def test_git_log_returns_string():
    result = git_log()
    assert isinstance(result, str)
    # Deve conter hash de commit (7 chars hex) ou mensagem de vazio
    assert len(result) > 0


def test_git_branch_current_returns_string():
    result = git_branch_current()
    assert isinstance(result, str)
    assert "branch" in result.lower() or "repositório" in result.lower()


def test_git_log_contains_commits():
    result = git_log()
    # O projeto tem commits, então não deve retornar "Nenhum"
    assert "Nenhum commit" not in result


# ── Arquivos ───────────────────────────────────────────────────────────

def test_create_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = create_file("python", "teste")
    assert result == "Arquivo 'teste.py' criado."
    assert (tmp_path / "teste.py").exists()


def test_create_file_with_extension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = create_file("arquivo", "notas.txt")
    assert "notas.txt" in result
    assert (tmp_path / "notas.txt").exists()


def test_resolve_file_finds_existing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "meu_arquivo.py").write_text("x = 1")
    path = _resolve_file("meu_arquivo.py")
    assert path is not None
    assert "meu_arquivo.py" in path


def test_resolve_file_finds_nested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.py").write_text("pass")
    path = _resolve_file("deep.py")
    assert path is not None


def test_resolve_file_returns_none_for_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _resolve_file("arquivo_inexistente_xyz.py") is None


def test_explain_file_returns_string(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code_file = tmp_path / "exemplo.py"
    code_file.write_text("def soma(a, b):\n    return a + b\n")

    # Monkeypatcha ask_ai para não chamar Ollama
    import modules.summarizer as summarizer
    monkeypatch.setattr(summarizer, "ask_ai", lambda p, **kw: "Esta função soma dois números.")

    result = explain_file("exemplo.py")
    assert isinstance(result, str)
    assert len(result) > 0


# ── Rotas no orchestrator ──────────────────────────────────────────────

def test_git_log_route(tmp_path):
    """Garante que variações de comando mapeiam para git_log."""
    import re
    from core.orchestrator import ROUTES

    log_pattern = next(p for p, h, _ in ROUTES if "git_log" in h)
    test_cases = [
        "mostra os últimos commits",
        "mostra os ultimos commits",
        "git log",
        "últimos commits",
    ]
    for cmd in test_cases:
        assert re.search(log_pattern, cmd.lower()), f"Não casou: {cmd!r}"


def test_git_status_route():
    import re
    from core.orchestrator import ROUTES

    status_pattern = next(p for p, h, _ in ROUTES if "git_status" in h)
    assert re.search(status_pattern, "o que mudou")
    assert re.search(status_pattern, "git status")


def test_run_tests_uses_pytest_when_tests_directory_exists(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)
    captured = {}

    class Result:
        returncode = 0
        stdout = "1 passed"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        return Result()

    monkeypatch.setattr("modules.dev_tools.subprocess.run", fake_run)
    result = run_tests()

    assert captured["command"][1:4] == ["-m", "pytest", "tests"]
    assert "Testes passaram" in result


# ── format_code ──────────────────────────────────────────────────────

def test_format_code_runs_black_and_isort(monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stdout = "1 file reformatted"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        return Result()

    monkeypatch.setattr("modules.dev_tools.subprocess.run", fake_run)
    result = format_code()

    assert len(calls) == 2
    assert calls[0][1:3] == ["-m", "black"]
    assert calls[1][1:3] == ["-m", "isort"]
    assert "black: ok" in result
    assert "isort: ok" in result


def test_format_code_reports_missing_tool(monkeypatch):
    def fake_run(command, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("modules.dev_tools.subprocess.run", fake_run)
    result = format_code()

    assert "não instalado" in result
