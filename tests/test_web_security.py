"""Testes de autenticação do dashboard."""

from web import app as web_app


class _WebSocket:
    def __init__(self, token="", origin="http://127.0.0.1:7755", host="127.0.0.1:7755"):
        self.cookies = {"pacoca_token": token} if token else {}
        self.headers = {"origin": origin, "host": host}


def test_websocket_requires_valid_password_token():
    web_app.set_password("segredo")
    try:
        assert not web_app._valid_websocket(_WebSocket())
        token = web_app._make_session_cookie()
        assert web_app._valid_websocket(_WebSocket(token=token))
    finally:
        web_app.set_password("")


def test_websocket_rejects_cross_origin_even_without_password():
    web_app.set_password("")
    socket = _WebSocket(origin="https://malicioso.example")
    assert not web_app._valid_websocket(socket)
