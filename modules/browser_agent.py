"""Automação local e supervisionada de navegador para o Paçoca.

O módulo usa Playwright de forma opcional. Nenhuma ação é executada sem uma
sessão explicitamente iniciada pelo usuário e os domínios são validados pela
lista de permissões configurada em ``core/config.yaml``.
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
                "O navegador do agente está desativado. Ative browser.enabled e "
                "configure browser.allowed_domains antes de usar."
            )

    def _validate_url(self, url: str) -> str:
        url = url.strip()
        if not re.match(r"^https?://", url, re.IGNORECASE):
            raise BrowserAgentError("A URL precisa começar com http:// ou https://.")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or not self.allowed_domains:
            raise BrowserAgentError("O domínio não está autorizado na configuração do navegador.")
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


def screenshot(path: str = "data/browser-last.png") -> str:
    return get_agent().screenshot(path)


def close() -> str:
    return get_agent().close()
