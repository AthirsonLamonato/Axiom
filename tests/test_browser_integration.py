import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


@pytest.fixture
def local_site(tmp_path):
    (tmp_path / "file.txt").write_text("download-ok", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        """<!doctype html><html><head><title>Paçoca Test</title></head><body>
        <h1>Agente local</h1><a href='/next.html'>Próxima</a>
        <form><input id='name'><select id='kind'><option value='a'>A</option><option value='b'>B</option></select>
        <button id='submit' type='button'>Enviar</button></form>
        <a id='download' href='/file.txt' download>Baixar</a>
        <script>document.querySelector('#submit').onclick=()=>document.body.dataset.sent='yes';</script>
        </body></html>""",
        encoding="utf-8",
    )
    (tmp_path / "next.html").write_text("<title>Next</title><p>next page</p>", encoding="utf-8")
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/index.html"
    finally:
        server.shutdown()
        server.server_close()


def test_browser_real_flow(local_site, tmp_path, monkeypatch):
    if os.environ.get("PACOCA_RUN_BROWSER_TESTS") != "1":
        pytest.skip("defina PACOCA_RUN_BROWSER_TESTS=1 para executar Chromium real")
    pytest.importorskip("playwright.sync_api")

    from modules.browser_agent import BrowserAgent

    class Config:
        def get(self, key, default=None):
            return {
                "browser.enabled": True,
                "browser.allow_all_domains": True,
                "browser.headless": True,
                "browser.profile_dir": str(tmp_path / "profile"),
            }.get(key, default)

    agent = BrowserAgent(Config())
    try:
        assert "Navegador iniciado" in agent.start(local_site)
        inspected = json.loads(agent.inspect())
        assert inspected["title"] == "Paçoca Test"
        assert "Agente local" in inspected["text"]
        assert "Próxima" in agent.links()
        assert "Campo preenchido" in agent.fill("#name", "Athirson")
        assert "Opção selecionada" in agent.select("#kind", "b")
        assert "Clique executado" in agent.click("#submit")
        screenshot = tmp_path / "data" / "shot.png"
        assert "Screenshot salvo" in agent.screenshot(str(screenshot))
        assert screenshot.exists()
        assert "Download salvo" in agent.download("#download", str(tmp_path / "data" / "downloads"))
        assert (tmp_path / "data" / "downloads" / "file.txt").exists()
    finally:
        agent.close()
