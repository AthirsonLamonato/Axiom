from types import SimpleNamespace

import pytest

from modules.browser_agent import BrowserAgent, BrowserAgentError
from modules.tools import known_tools, validate


class FakeConfig:
    def __init__(self, data):
        self.data = data

    def get(self, key, default=None):
        node = self.data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


def make_agent(**browser):
    return BrowserAgent(FakeConfig({"browser": browser}))


def test_browser_is_disabled_by_default():
    agent = make_agent(enabled=False, allowed_domains=[])
    with pytest.raises(BrowserAgentError, match="desativado"):
        agent.start()


def test_about_blank_is_allowed_for_start():
    agent = make_agent(enabled=True, allowed_domains=["example.com"])
    assert agent._validate_url("https://example.com/login") == "https://example.com/login"


def test_domain_allowlist_rejects_untrusted_hosts():
    agent = make_agent(enabled=True, allowed_domains=["example.com"])
    with pytest.raises(BrowserAgentError, match="não autorizado"):
        agent._validate_url("https://evil-example.com/")


def test_domain_allowlist_accepts_subdomains():
    agent = make_agent(enabled=True, allowed_domains=["example.com"])
    assert agent._validate_url("https://app.example.com/dashboard").startswith("https://app.")


def test_allow_all_domains_accepts_any_http_site():
    agent = make_agent(enabled=True, allow_all_domains=True, allowed_domains=[])
    assert agent._validate_url("https://news.ycombinator.com/") == "https://news.ycombinator.com/"


def test_non_http_urls_are_rejected():
    agent = make_agent(enabled=True, allowed_domains=["example.com"])
    with pytest.raises(BrowserAgentError, match="http"):
        agent._validate_url("file:///etc/passwd")


def test_browser_tools_are_registered_with_safe_defaults():
    expected = {
        "browser_start",
        "browser_navigate",
        "browser_inspect",
        "browser_click",
        "browser_fill",
        "browser_screenshot",
        "browser_tabs",
        "browser_switch_tab",
        "browser_back",
        "browser_forward",
        "browser_wait",
        "browser_press",
        "browser_select",
        "browser_links",
        "browser_download",
        "browser_close",
    }
    assert expected <= known_tools()
    assert validate("browser_close", {})[1] == ""
    assert validate("browser_navigate", {"url": "https://example.com"})[1] == ""


def test_screenshot_path_cannot_escape_data_directory():
    agent = make_agent(enabled=True, allow_all_domains=True)
    with pytest.raises(BrowserAgentError, match="dentro de data"):
        agent.screenshot("../../outside.png")


def test_browser_advanced_tools_validate_arguments():
    assert validate("browser_switch_tab", {"index": 0})[1] == ""
    assert validate("browser_wait", {"seconds": 2})[1] == ""
    assert validate("browser_press", {"selector": "#q", "key": "Enter"})[1] == ""
    assert validate("browser_select", {"selector": "select", "value": "br"})[1] == ""
    assert validate("browser_links", {"max_items": 10})[1] == ""
    assert validate("browser_download", {"selector": "a.download"})[1] == ""


def test_browser_fill_requires_selector_and_value():
    model, error = validate("browser_fill", {"selector": "#email"})
    assert model is None
    assert error
