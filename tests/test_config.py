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
