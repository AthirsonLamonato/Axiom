"""Testes para modules/intent.py — NLU pipeline (camadas 1, 2 e cache)."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── _normalize_for_clf ─────────────────────────────────────────────────

class TestNormalizeForClf:
    def setup_method(self):
        from modules.intent import _normalize_for_clf
        self.norm = _normalize_for_clf

    def test_play_verb_replaced_with_query(self):
        assert "[QUERY]" in self.norm("toca Linkin Park")

    def test_volume_not_misclassified_as_play(self):
        """'coloca o volume em 45' não deve virar [QUERY]."""
        result = self.norm("coloca o volume em 45")
        assert "volume" in result
        assert "[QUERY]" not in result

    def test_browser_preserved(self):
        result = self.norm("pesquisa python no firefox")
        assert "[BROWSER]" in result
        assert "[QUERY]" in result

    def test_web_search_no_browser(self):
        result = self.norm("pesquisa sobre machine learning")
        assert "[QUERY]" in result
        assert "[BROWSER]" not in result

    def test_number_slot(self):
        result = self.norm("volume 60")
        assert "[NUM]" in result

    def test_git_branch_slot(self):
        result = self.norm("cria branch feature/login")
        assert "[SLOT]" in result

    def test_encerre_app_slot(self):
        result = self.norm("encerre o chrome")
        assert "[APP]" in result


# ── Classificador TF-IDF (camada 2) ───────────────────────────────────

class TestClassifier:
    """Requer scikit-learn. Pulado se indisponível."""

    @pytest.fixture(autouse=True)
    def require_sklearn(self):
        pytest.importorskip("sklearn")

    def setup_method(self):
        from modules.intent import _parse_with_classifier, _clf_state
        self._parse = _parse_with_classifier
        self._state = _clf_state

    def _classify(self, text):
        calls, confidence = self._parse(text)
        return calls, confidence

    def test_toca_musica_classified_as_control_media(self):
        calls, conf = self._classify("toca Eminem")
        assert calls, "classificador não retornou resultado"
        assert calls[0]["name"] == "control_media"
        assert calls[0]["arguments"]["action"] == "play"

    def test_pausa_classified(self):
        calls, conf = self._classify("para a música")
        assert calls
        assert calls[0]["name"] == "control_media"
        assert calls[0]["arguments"]["action"] == "pause"

    def test_proxima_musica_classified(self):
        calls, conf = self._classify("próxima música")
        assert calls
        assert calls[0]["arguments"]["action"] == "next"

    def test_volume_not_misclassified_as_play(self):
        calls, conf = self._classify("coloca o volume em 45")
        assert calls
        assert calls[0]["name"] == "set_volume"

    def test_confidence_above_threshold_for_clear_commands(self):
        from modules.intent import _CONFIDENCE_THRESHOLD
        _, conf = self._classify("toca uma música do Eminem")
        assert conf >= _CONFIDENCE_THRESHOLD, f"confiança {conf:.2f} abaixo do limiar"

    def test_encerre_chrome_close_application(self):
        calls, conf = self._classify("encerre o chrome")
        assert calls
        assert calls[0]["name"] == "close_application"

    def test_web_search_no_browser(self):
        calls, conf = self._classify("pesquisa sobre machine learning")
        assert calls
        assert calls[0]["name"] == "web_search"

    def test_open_browser_with_browser_keyword(self):
        calls, conf = self._classify("pesquisa python no firefox")
        assert calls
        assert calls[0]["name"] == "open_browser"


# ── Cache ──────────────────────────────────────────────────────────────

class TestCache:
    def setup_method(self):
        from modules import intent
        intent._get_intent_cache().clear()
        self.module = intent

    def test_cache_hit_after_store(self):
        from modules.intent import _cache_set, _cache_get
        _cache_set("toca eminem", [{"name": "control_media", "arguments": {"action": "play"}}])
        result = _cache_get("toca eminem")
        assert result is not None
        assert result[0]["name"] == "control_media"

    def test_cache_normalizes_key(self):
        from modules.intent import _cache_set, _cache_get
        _cache_set("Toca Eminem", [{"name": "control_media", "arguments": {}}])
        assert _cache_get("toca eminem") is not None

    def test_empty_list_not_cached(self):
        from modules.intent import _cache_set, _cache_get
        _cache_set("comando que falhou", [])
        assert _cache_get("comando que falhou") is None

    def test_cache_expires_with_future_time(self, monkeypatch):
        import time as _real_time
        from modules.intent import _cache_set, _cache_get, _CACHE_TTL
        _cache_set("toca linkin park", [{"name": "control_media", "arguments": {}}])
        # _TTLCache (core/providers.py) usa time.monotonic(), não time.time()
        future = _real_time.monotonic() + _CACHE_TTL + 1
        monkeypatch.setattr("core.providers.time.monotonic", lambda: future)
        assert _cache_get("toca linkin park") is None


# ── Contexto de diálogo ────────────────────────────────────────────────

class TestDialogContext:
    def setup_method(self):
        from modules import intent
        intent._dialog_ctx.clear()
        self.module = intent

    def test_update_appends_intent(self):
        from modules.intent import _update_dialog_ctx, _dialog_ctx
        _update_dialog_ctx("toca eminem", [{"name": "control_media", "arguments": {"action": "play"}}])
        assert len(_dialog_ctx) == 1
        assert _dialog_ctx[0]["intent"] == "control_media"

    def test_empty_calls_not_appended(self):
        from modules.intent import _update_dialog_ctx, _dialog_ctx
        _update_dialog_ctx("algo", [])
        assert len(_dialog_ctx) == 0

    def test_context_prompt_contains_recent_command(self):
        from modules.intent import _update_dialog_ctx, _dialog_context_prompt
        _update_dialog_ctx("toca eminem", [{"name": "control_media", "arguments": {"action": "play"}}])
        prompt = _dialog_context_prompt()
        assert "toca eminem" in prompt
        assert "control_media" in prompt

    def test_maxlen_respected(self):
        from modules.intent import _update_dialog_ctx, _dialog_ctx
        for i in range(10):
            _update_dialog_ctx(f"cmd {i}", [{"name": "answer_question", "arguments": {"question": f"q{i}"}}])
        assert len(_dialog_ctx) <= 5


# ── _needs_confirmation ────────────────────────────────────────────────

class TestNeedsConfirmation:
    def test_close_application_requires_confirmation(self):
        from modules.intent import _needs_confirmation
        assert _needs_confirmation("close_application", {"name": "discord"})

    def test_git_push_requires_confirmation(self):
        from modules.intent import _needs_confirmation
        assert _needs_confirmation("git_operation", {"operation": "push"})

    def test_git_commit_requires_confirmation(self):
        from modules.intent import _needs_confirmation
        assert _needs_confirmation("git_operation", {"operation": "commit"})

    def test_git_pull_requires_confirmation(self):
        from modules.intent import _needs_confirmation
        assert _needs_confirmation("git_operation", {"operation": "pull"})

    def test_git_status_no_confirmation(self):
        from modules.intent import _needs_confirmation
        assert not _needs_confirmation("git_operation", {"operation": "status"})

    def test_control_media_no_confirmation(self):
        from modules.intent import _needs_confirmation
        assert not _needs_confirmation("control_media", {"action": "pause"})


# ── _confirm_action (não-interativo) ───────────────────────────────────

class TestConfirmActionNonInteractive:
    def test_denied_outside_tty(self, monkeypatch):
        """Fora de um TTY a ação crítica deve ser negada automaticamente."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        from modules.intent import _confirm_action
        result = _confirm_action("close_application", {"name": "discord"})
        assert result is False
def test_media_commands_use_fast_deterministic_route():
    from modules.intent import classify_local

    assert classify_local("pausa o spotify") == [
        {"name": "control_media", "arguments": {"action": "pause"}}
    ]
    assert classify_local("toca Coldplay") == [
        {"name": "control_media", "arguments": {"action": "play", "query": "Coldplay"}}
    ]


def test_generic_play_is_valid_and_media_actions_are_normalized():
    from modules.tools import validate

    generic, error = validate("control_media", {"action": "play"})
    assert error == ""
    assert generic.action == "play"
    normalized, error = validate("control_media", {"action": "pausar"})
    assert error == ""
    assert normalized.action == "pause"


def test_natural_media_variations_stay_local():
    from modules.intent import classify_local

    assert classify_local("volta a tocar") == [
        {"name": "control_media", "arguments": {"action": "resume"}}
    ]
    assert classify_local("dá play") == [
        {"name": "control_media", "arguments": {"action": "resume"}}
    ]
    assert classify_local("dá play Coldplay") == [
        {"name": "control_media", "arguments": {"action": "play", "query": "Coldplay"}}
    ]


def test_invalid_tool_args_return_friendly_clarification():
    from modules.intent import _execute_tool

    response = _execute_tool("set_volume", {})

    assert response == "Não consegui entender todos os detalhes desse comando. Pode reformular?"


def test_voice_politeness_and_common_names_are_normalized(monkeypatch):
    monkeypatch.setattr("storage.memory.apply_vocabulary", lambda text: text)
    from modules.intent import classify_local
    from modules.learner import correct_transcription

    assert correct_transcription("Você pode abrir pra mim o Spot Fire?") == "abrir o Spotify?"
    assert classify_local(correct_transcription("Você pode abrir pra mim o Spot Fire?")) == [
        {"name": "open_application", "arguments": {"name": "Spotify"}}
    ]
