"""
tests/conftest.py — Configuração do pytest para o Paçoca

- Testes de integração (hardware, rede, microfone) são marcados com
  @pytest.mark.integration e pulados por padrão.
- Para rodar testes de integração: pytest -m integration
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: testes que requerem rede, hardware ou serviços externos. "
        "Pulados por padrão — rode com: pytest -m integration",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("-m", default="") == "integration":
        skip_integration = pytest.mark.skip(reason="Pulado por padrão. Use: pytest -m integration")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
