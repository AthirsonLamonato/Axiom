"""Testes do catálogo e seleção de modelos locais."""
from core.ai_catalog import list_models, recommend_model, recommended_config


def test_low_memory_selects_small_tool_model():
    model = recommend_model(3.5)
    assert model.name == "qwen3:1.7b"
    assert model.tools is True


def test_balanced_memory_selects_qwen3_4b():
    model = recommend_model(6.0)
    assert model.name == "qwen3:4b"
    assert model.tools is True


def test_catalog_tools_only_excludes_reasoning_without_tools():
    models = list_models(tools_only=True)
    assert models
    assert all(item["tools"] for item in models)


def test_recommended_config_is_local_and_zero_cost():
    config = recommended_config(6.0)
    assert config["provider"] == "ollama"
    assert config["embeddings_provider"] == "ollama"
    assert config["model"] == "qwen3:4b"
