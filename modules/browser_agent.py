"""Automação local e supervisionada de navegador para o Paçoca.

O módulo usa Playwright de forma opcional. Nenhuma ação é executada sem uma
sessão explicitamente iniciada pelo usuário. O modo amplo permite qualquer
URL http(s); o modo restrito usa a lista de domínios configurada em
``core/config.yaml``.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

try:  # dependência opcional; o Paçoca continua inicializando sem ela
    from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
except ImportError:  # pragma: no cover - coberto por teste de instalação
    Browser = BrowserContext = Page = Any  # type: ignore[misc,assignment]
    sync_playwright = None  # type: ignore[assignment]


class BrowserAgentError(RuntimeError):
    """Erro seguro e legível nas operações do navegador."""


class BrowserAgent:
    """Gerencia uma única sessão persistente e controlada de navegador."""

    def __init__(self, config: Any | None = None):
        if config is None:
            from core.config import Config
            config = Config()
        self.config = config
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("browser.enabled", False))

    @property
    def allowed_domains(self) -> list[str]:
        domains = self.config.get("browser.allowed_domains", []) or []
        return [str(d).lower().strip().lstrip(".") for d in domains if str(d).strip()]

    def _require_dependency(self) -> None:
        if sync_playwright is None:
            raise BrowserAgentError(
                "Automação de navegador indisponível. Instale a dependência "
                "opcional com: pip install playwright && python -m playwright install chromium"
            )

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise BrowserAgentError(
                "O navegador do agente está desativado. Ative browser.enabled antes de usar."
            )

    def _validate_url(self, url: str) -> str:
        url = url.strip()
        if not re.match(r"^https?://", url, re.IGNORECASE):
            raise BrowserAgentError("A URL precisa começar com http:// ou https://.")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            raise BrowserAgentError("A URL não contém um domínio válido.")
        if bool(self.config.get("browser.allow_all_domains", False)):
            return url
        if not self.allowed_domains:
            raise BrowserAgentError("Nenhum domínio autorizado na configuração restrita do navegador.")
        allowed = any(host == domain or host.endswith("." + domain) for domain in self.allowed_domains)
        if not allowed:
            raise BrowserAgentError(f"Domínio não autorizado: {host}")
        return url

    def _require_page(self) -> Page:
        if self._page is None:
            raise BrowserAgentError("Nenhuma sessão do navegador está aberta. Use browser_start primeiro.")
        return self._page

    def start(self, url: str = "about:blank") -> str:
        self._require_enabled()
        self._require_dependency()
        if self._page is not None:
            return f"Sessão já aberta: {self._page.url}"
        if url != "about:blank":
            url = self._validate_url(url)
        user_data_dir = Path(self.config.get("browser.profile_dir", "data/browser-profile"))
        user_data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=bool(self.config.get("browser.headless", False)),
            viewport=None,
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        if url != "about:blank":
            self._page.goto(url, wait_until="domcontentloaded")
        return f"Navegador iniciado em {self._page.url}"

    def navigate(self, url: str) -> str:
        page = self._require_page()
        url = self._validate_url(url)
        page.goto(url, wait_until="domcontentloaded")
        return f"Página aberta: {page.title()} ({page.url})"

    def inspect(self, max_chars: int = 6000) -> str:
        page = self._require_page()
        title = page.title()
        text = page.locator("body").inner_text(timeout=5000)
        text = re.sub(r"\s+", " ", text).strip()
        payload = {"title": title, "url": page.url, "text": text[:max_chars]}
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def click(self, selector: str) -> str:
        page = self._require_page()
        if not selector.strip():
            raise BrowserAgentError("O seletor de clique não pode ser vazio.")
        page.locator(selector).first.click(timeout=10000)
        return f"Clique executado: {selector}"

    def fill(self, selector: str, value: str) -> str:
        page = self._require_page()
        if not selector.strip():
            raise BrowserAgentError("O seletor do campo não pode ser vazio.")
        page.locator(selector).first.fill(value)
        return f"Campo preenchido: {selector}"

    def tabs(self) -> str:
        context = self._context
        if context is None:
            raise BrowserAgentError("Nenhuma sessão do navegador está aberta. Use browser_start primeiro.")
        payload = [{"index": i, "url": page.url, "title": page.title()} for i, page in enumerate(context.pages)]
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def switch_tab(self, index: int) -> str:
        context = self._context
        if context is None:
            raise BrowserAgentError("Nenhuma sessão do navegador está aberta. Use browser_start primeiro.")
        pages = context.pages
        if index < 0 or index >= len(pages):
            raise BrowserAgentError(f"Aba inexistente: {index}. Existem {len(pages)} aba(s).")
        self._page = pages[index]
        return f"Aba selecionada: {index} — {self._page.title()} ({self._page.url})"

    def back(self) -> str:
        page = self._require_page()
        page.go_back(wait_until="domcontentloaded")
        return f"Voltou para: {page.title()} ({page.url})"

    def forward(self) -> str:
        page = self._require_page()
        page.go_forward(wait_until="domcontentloaded")
        return f"Avançou para: {page.title()} ({page.url})"

    def wait(self, seconds: float = 1.0) -> str:
        page = self._require_page()
        seconds = max(0.1, min(float(seconds), 20.0))
        page.wait_for_timeout(int(seconds * 1000))
        return f"Aguardou {seconds:g} segundo(s)."

    def press(self, selector: str, key: str) -> str:
        page = self._require_page()
        if not selector.strip() or not key.strip():
            raise BrowserAgentError("Seletor e tecla são obrigatórios.")
        page.locator(selector).first.press(key, timeout=10000)
        return f"Tecla {key} pressionada em {selector}."

    def select(self, selector: str, value: str) -> str:
        page = self._require_page()
        if not selector.strip() or not value.strip():
            raise BrowserAgentError("Seletor e valor são obrigatórios.")
        page.locator(selector).first.select_option(value)
        return f"Opção selecionada em {selector}."

    def links(self, max_items: int = 30) -> str:
        page = self._require_page()
        max_items = max(1, min(int(max_items), 100))
        rows = page.locator("a").evaluate_all(
            """(els, limit) => els.slice(0, limit).map(a => ({text: (a.innerText || '').trim(), href: a.href}))""",
            max_items,
        )
        return json.dumps(rows, ensure_ascii=False, indent=2)

    def download(self, selector: str, path: str = "data/downloads") -> str:
        page = self._require_page()
        if not selector.strip():
            raise BrowserAgentError("O seletor do download não pode ser vazio.")
        base = (Path.cwd() / "data" / "downloads").resolve()
        requested = Path(path)
        output_dir = (base / requested).resolve() if not requested.is_absolute() else requested.resolve()
        if base not in output_dir.parents and output_dir != base:
            raise BrowserAgentError("Downloads só podem ser salvos em data/downloads.")
        output_dir.mkdir(parents=True, exist_ok=True)
        with page.expect_download(timeout=15000) as download_info:
            page.locator(selector).first.click(timeout=10000)
        download = download_info.value
        destination = output_dir / Path(download.suggested_filename).name
        download.save_as(str(destination))
        return f"Download salvo em {destination}"

    def screenshot(self, path: str = "data/browser-last.png") -> str:
        page = self._require_page()
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output), full_page=True)
        return f"Screenshot salvo em {output}"

    def close(self) -> str:
        if self._context is not None:
            self._context.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._context = self._page = self._playwright = None
        return "Sessão do navegador encerrada."


_AGENT: BrowserAgent | None = None


def get_agent() -> BrowserAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = BrowserAgent()
    return _AGENT


def start(url: str = "about:blank") -> str:
    return get_agent().start(url)


def navigate(url: str) -> str:
    return get_agent().navigate(url)


def inspect(max_chars: int = 6000) -> str:
    return get_agent().inspect(max_chars)


def click(selector: str) -> str:
    return get_agent().click(selector)


def fill(selector: str, value: str) -> str:
    return get_agent().fill(selector, value)


def tabs() -> str:
    return get_agent().tabs()


def switch_tab(index: int) -> str:
    return get_agent().switch_tab(index)


def back() -> str:
    return get_agent().back()


def forward() -> str:
    return get_agent().forward()


def wait(seconds: float = 1.0) -> str:
    return get_agent().wait(seconds)


def press(selector: str, key: str) -> str:
    return get_agent().press(selector, key)


def select(selector: str, value: str) -> str:
    return get_agent().select(selector, value)


def links(max_items: int = 30) -> str:
    return get_agent().links(max_items)


def download(selector: str, path: str = "data/downloads") -> str:
    return get_agent().download(selector, path)


def screenshot(path: str = "data/browser-last.png") -> str:
    return get_agent().screenshot(path)


def close() -> str:
    return get_agent().close()
