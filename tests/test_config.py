"""Testes para core/config.py"""

import os
import tempfile
import pytest
import yaml

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import Config


@pytest.fixture
def config_file(tmp_path):
    data = {
        "profile": {"active": "work"},
        "tts": {"enabled": True, "rate": 175},
        "ai": {"provider": "ollama", "model": "llama3"},
        "logging": {"level": "INFO", "file": "logs/pacoca.log", "max_mb": 10},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def config(config_file):
    return Config(config_file)


def test_load_simple_key(config):
    assert config.get("profile.active") == "work"


def test_load_nested_key(config):
    assert config.get("tts.rate") == 175


def test_default_value(config):
    assert config.get("nonexistent.key", "default") == "default"


def test_default_none_when_missing(config):
    assert config.get("missing") is None


def test_set_runtime(config):
    config.set("tts.enabled", False)
    assert config.get("tts.enabled") is False


def test_set_creates_nested(config):
    config.set("new.nested.key", 42)
    assert config.get("new.nested.key") == 42


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        Config("/nonexistent/path/config.yaml")


def test_all_returns_dict(config):
    assert isinstance(config.all(), dict)
    assert "profile" in config.all()


def test_local_config_deeply_overrides_without_losing_siblings(tmp_path):
    base = tmp_path / "config.yaml"
    local = tmp_path / "config.local.yaml"
    base.write_text(
        yaml.safe_dump({"whatsapp": {"enabled": True, "allowed_numbers": []}}),
        encoding="utf-8",
    )
    local.write_text(
        yaml.safe_dump({"whatsapp": {"allowed_numbers": ["+5511999991234"]}}),
        encoding="utf-8",
    )

    loaded = Config(str(base), local_path=str(local))

    assert loaded.get("whatsapp.enabled") is True
    assert loaded.get("whatsapp.allowed_numbers") == ["+5511999991234"]


def test_invalid_local_config_fails_explicitly(tmp_path):
    base = tmp_path / "config.yaml"
    local = tmp_path / "config.local.yaml"
    base.write_text(yaml.safe_dump({"profile": {"active": "work"}}), encoding="utf-8")
    local.write_text("- item", encoding="utf-8")

    with pytest.raises(ValueError, match="Config local"):
        Config(str(base), local_path=str(local))
