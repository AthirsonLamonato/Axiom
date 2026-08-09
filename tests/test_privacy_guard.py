import sys
import types

from modules import clipboard_tools, privacy_guard, screen_reader


def test_sanitize_masks_sensitive_content(monkeypatch):
    monkeypatch.setattr(privacy_guard, "redaction_enabled", lambda: True)
    result = privacy_guard.sanitize_text("alice@example.com +55 11 99999-1234 token=abc")
    assert "alice@example.com" not in result
    assert "99999-1234" not in result
    assert "abc" not in result


def test_clipboard_read_masks_before_display(monkeypatch):
    fake = types.ModuleType("pyperclip")
    fake.paste = lambda: "alice@example.com"
    monkeypatch.setitem(sys.modules, "pyperclip", fake)
    monkeypatch.setattr(privacy_guard, "redaction_enabled", lambda: True)
    result = clipboard_tools.read_clipboard()
    assert "alice@example.com" not in result
    assert "a***@example.com" in result


def test_screenshot_is_blocked_before_capture(monkeypatch):
    monkeypatch.setattr(privacy_guard, "screenshots_allowed", lambda: False)
    monkeypatch.setattr(
        screen_reader,
        "_grab_screen",
        lambda: (_ for _ in ()).throw(AssertionError("captura não deve ocorrer")),
    )
    assert "bloqueado" in screen_reader.save_screenshot().lower()
