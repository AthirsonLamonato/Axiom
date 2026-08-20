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


def test_distributed_config_requires_plan_approval_by_default():
    repo_config = os.path.join(os.path.dirname(__file__), "..", "core", "config.yaml")
    distributed = Config(repo_config)
    assert distributed.get("agent.require_plan_approval") is True
    assert distributed.get("ai.provider") == "ollama"



def test_profile_policy_allows_work_profile_high_risk_by_default():
    from core.security_policy import check_tool

    allowed, reason = check_tool("close_application", "high")
    assert allowed is True
    assert reason == ""


def test_profile_policy_blocks_high_risk_for_restricted_profile(monkeypatch):
    from core import security_policy

    monkeypatch.setattr(
        security_policy,
        "_config_data",
        lambda: {
            "profile": {"active": "focus"},
            "security": {
                "profile_policies": {
                    "focus": {"max_risk": "medium", "allowed_tools": [], "denied_tools": []}
                }
            },
        },
    )
    allowed, reason = security_policy.check_tool("close_application", "high")
    assert allowed is False
    assert "risco máximo" in reason
