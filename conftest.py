import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: testes que requerem hardware real (microfone, GPU, rede). "
        "Execute com: pytest -m integration",
    )


def pytest_collection_modifyitems(config, items):
    """Pula testes de integração por padrão, a menos que -m integration seja passado."""
    if config.getoption("-m", default="") == "integration":
        return
    skip_integration = pytest.mark.skip(reason="teste de integração: use -m integration para rodar")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
