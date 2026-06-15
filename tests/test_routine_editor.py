"""Testes para persistência do editor de rotinas."""

import yaml

from core.config import Config
from main import _edit_routines


def test_remove_routine_persists_to_yaml(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {"routines": {"teste": {"name": "Teste", "steps": []}}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    config = Config(str(path))
    answers = iter(["r", "teste", "s"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    _edit_routines(config)

    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "teste" not in saved["routines"]
