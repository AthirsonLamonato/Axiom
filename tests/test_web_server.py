"""Testes para ciclo de vida do servidor web."""

from modules import web_server


class _Server:
    should_exit = False


class _Thread:
    def __init__(self):
        self.joined = False

    def is_alive(self):
        return not self.joined

    def join(self, timeout=None):
        self.joined = True


def test_stop_signals_uvicorn_and_waits_for_thread(monkeypatch):
    server = _Server()
    thread = _Thread()
    monkeypatch.setattr(web_server, "_server", server)
    monkeypatch.setattr(web_server, "_server_thread", thread)
    monkeypatch.setattr(web_server, "_server_running", True)

    result = web_server.stop()

    assert server.should_exit is True
    assert thread.joined is True
    assert result == "Servidor web encerrado."
