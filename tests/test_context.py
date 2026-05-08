"""Testes para storage/context.py"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import storage.context as ctx


@pytest.fixture(autouse=True)
def reset():
    ctx._memory.clear()
    yield
    ctx._memory.clear()


def test_add_e_get():
    ctx.add("oi", "olá")
    turns = ctx.get_turns()
    assert len(turns) == 1
    assert turns[0] == ("oi", "olá")


def test_add_ignora_vazios():
    ctx.add("", "resposta")
    ctx.add("comando", "")
    assert ctx.get_turns() == []


def test_max_turns_nao_ultrapassa():
    for i in range(ctx.MAX_TURNS + 5):
        ctx.add(f"cmd{i}", f"resp{i}")
    assert len(ctx.get_turns()) == ctx.MAX_TURNS


def test_max_turns_mantem_mais_recentes():
    for i in range(ctx.MAX_TURNS + 3):
        ctx.add(f"cmd{i}", f"resp{i}")
    turns = ctx.get_turns()
    assert turns[-1][0].startswith("cmd")
    ultimo_idx = int(turns[-1][0].replace("cmd", ""))
    assert ultimo_idx == ctx.MAX_TURNS + 2


def test_clear():
    ctx.add("x", "y")
    result = ctx.clear()
    assert ctx.get_turns() == []
    assert "limpo" in result.lower()


def test_show_vazio():
    result = ctx.show()
    assert "Nenhuma" in result


def test_show_com_historico():
    ctx.add("como funciona python", "Python é uma linguagem...")
    result = ctx.show()
    assert "python" in result.lower()
    assert "1." in result


def test_build_context_prompt_sem_historico():
    result = ctx.build_context_prompt("nova pergunta")
    assert result == "nova pergunta"


def test_build_context_prompt_com_historico():
    ctx.add("o que é python", "Uma linguagem de programação.")
    result = ctx.build_context_prompt("e como instalo?")
    assert "Histórico" in result
    assert "python" in result.lower()
    assert "e como instalo?" in result
