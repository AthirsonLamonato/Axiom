"""Testes de endpoints do dashboard: rate limit, sessão, CSRF."""

import time

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from web import app as web_app  # noqa: E402


class _FakeConfig:
    def __init__(self):
        self._data = {"routines": {}}
        self._path = "/tmp/_pacoca_test_config.yaml"

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value


class _FakeOrchestrator:
    def __init__(self):
        self.config = _FakeConfig()


@pytest.fixture
def client():
    return TestClient(web_app.app)


@pytest.fixture(autouse=True)
def _reset_web_state():
    web_app.set_password("")
    web_app._login_attempts.clear()
    with web_app._session_lock:
        web_app._last_seen = 0.0
    yield
    web_app.set_password("")
    web_app._login_attempts.clear()
    with web_app._session_lock:
        web_app._last_seen = 0.0


def test_login_rate_limited_after_too_many_failures(client):
    web_app.set_password("segredo")
    for _ in range(web_app._login_max_attempts()):
        resp = client.post("/login", data={"password": "errada"})
        assert resp.status_code == 401
    resp = client.post("/login", data={"password": "errada"})
    assert resp.status_code == 429

    resp = client.post("/login", data={"password": "segredo"})
    assert resp.status_code == 429


def test_login_success_sets_cookie_and_touches_session(client):
    web_app.set_password("segredo")
    resp = client.post("/login", data={"password": "segredo"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "pacoca_token" in resp.cookies
    assert web_app._last_seen > 0.0


def test_session_expires_after_timeout(client, monkeypatch):
    web_app.set_password("segredo")
    monkeypatch.setattr(web_app, "_session_timeout_s", lambda: 0)
    client.post("/login", data={"password": "segredo"})
    time.sleep(0.01)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert resp.headers["location"].startswith("/login")


def test_dashboard_injects_csrf_header(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert web_app._CSRF_TOKEN in resp.text
    assert "hx-headers" in resp.text


class _FakeWebSocket:
    def __init__(self, token):
        self.cookies = {"pacoca_token": token}
        self.headers = {}


def test_websocket_rejects_token_after_session_expired(monkeypatch):
    """Regressão: WS deve respeitar security.session_timeout_min como o HTTP,
    em vez de só validar o token (sessão nunca expirava para WS)."""
    web_app.set_password("segredo")
    token = web_app._token_for("segredo")
    ws = _FakeWebSocket(token)

    assert web_app._valid_websocket(ws) is True

    monkeypatch.setattr(web_app, "_session_expired", lambda: True)
    assert web_app._valid_websocket(ws) is False


def test_routines_add_rejects_missing_csrf_token(client):
    web_app._orchestrator = _FakeOrchestrator()
    try:
        resp = client.post(
            "/api/routines/add",
            data={"name": "r1", "label": "Rotina 1", "action": "notify", "target": "oi"},
        )
        assert resp.status_code == 403
    finally:
        web_app._orchestrator = None


def test_routines_add_accepts_valid_csrf_token(client):
    web_app._orchestrator = _FakeOrchestrator()
    try:
        resp = client.post(
            "/api/routines/add",
            data={"name": "r1", "label": "Rotina 1", "action": "notify", "target": "oi"},
            headers={"X-CSRF-Token": web_app._CSRF_TOKEN},
        )
        assert resp.status_code == 200
        assert "r1" in resp.text
    finally:
        web_app._orchestrator = None


def test_docs_page_renders(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "Documenta" in resp.text


def test_metrics_page_renders(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
