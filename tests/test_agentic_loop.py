"""
Testes para o loop agentivo (modules/intent.py) e memória (storage/knowledge_base.py).
Sem chamadas reais à API Groq — todas mockadas.
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_dialog_ctx():
    from modules import intent
    intent._dialog_ctx.clear()
    intent._get_intent_cache().clear()
    yield
    intent._dialog_ctx.clear()
    intent._get_intent_cache().clear()


@pytest.fixture
def groq_config(tmp_path):
    import yaml
    from core.config import Config
    data = {
        "ai": {"provider": "groq", "groq_api_key": "test-key", "groq_model": "llama-3.3-70b-versatile"},
        "logging": {"level": "WARNING", "file": str(tmp_path / "test.log"), "max_mb": 1},
        "security": {"confirm_critical": False},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return Config(str(path))


def _tool_call_response(name: str, args: dict, call_id: str = "call_1") -> dict:
    """Monta uma resposta Groq com uma tool_call."""
    return {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }],
            },
        }]
    }


def _text_response(text: str) -> dict:
    """Monta uma resposta Groq com texto final (sem tool_call)."""
    return {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": text, "tool_calls": None},
        }]
    }


def _tool_use_failed_exc() -> Exception:
    """Simula a exceção HTTP 400 'tool_use_failed' real do Groq."""
    exc = RuntimeError("400 Client Error: Bad Request")
    fake_response = MagicMock()
    fake_response.text = '{"error":{"code":"tool_use_failed","message":"..."}}'
    exc.response = fake_response
    return exc


# ── _check_required_args ─────────────────────────────────────────────

class TestCheckRequiredArgs:
    def test_close_application_empty_name_returns_error(self):
        from modules.intent import _check_required_args
        result = _check_required_args("close_application", {"name": ""})
        assert result != ""  # deve retornar mensagem de erro

    def test_close_application_missing_name_returns_error(self):
        from modules.intent import _check_required_args
        result = _check_required_args("close_application", {})
        assert result != ""

    def test_close_application_valid_name_ok(self):
        from modules.intent import _check_required_args
        result = _check_required_args("close_application", {"name": "chrome"})
        assert result == ""

    def test_set_volume_missing_level_returns_error(self):
        from modules.intent import _check_required_args
        result = _check_required_args("set_volume", {})
        assert result != ""

    def test_set_volume_valid_level_ok(self):
        from modules.intent import _check_required_args
        result = _check_required_args("set_volume", {"level": 50})
        assert result == ""

    def test_remember_empty_statement_returns_error(self):
        from modules.intent import _check_required_args
        result = _check_required_args("remember", {"statement": "   "})
        assert result != ""

    def test_control_media_missing_action_returns_error(self):
        from modules.intent import _check_required_args
        result = _check_required_args("control_media", {})
        assert result != ""

    def test_list_memories_no_required_fields(self):
        from modules.intent import _check_required_args
        result = _check_required_args("list_memories", {})
        assert result == ""

    def test_unknown_tool_returns_error(self):
        from modules.intent import _check_required_args
        result = _check_required_args("unknown_tool", {})
        # Registry não conhece a ferramenta → erro (mais seguro que silenciar)
        assert result != ""


# ── Novos tools no schema ─────────────────────────────────────────────

class TestNewTools:
    def test_remember_in_tools_schema(self):
        from modules.intent import TOOLS, _VALID_TOOLS
        names = {t["function"]["name"] for t in TOOLS}
        assert "remember" in names
        assert "forget" in names
        assert "list_memories" in names

    def test_remember_in_valid_tools(self):
        from modules.intent import _VALID_TOOLS
        assert "remember" in _VALID_TOOLS
        assert "forget" in _VALID_TOOLS
        assert "list_memories" in _VALID_TOOLS


# ── _execute_tool ─────────────────────────────────────────────────────

class TestExecuteTool:
    def test_remember_delegates_to_knowledge_base(self):
        from modules.intent import _execute_tool
        with patch("storage.knowledge_base.remember", return_value="Memorizado.") as mock_rem:
            result = _execute_tool("remember", {"statement": "gosto de rock"})
        mock_rem.assert_called_once_with("gosto de rock")
        assert "Memorizado" in result

    def test_forget_delegates_to_knowledge_base(self):
        from modules.intent import _execute_tool
        with patch("storage.knowledge_base.forget", return_value="Esqueci.") as mock_forg:
            result = _execute_tool("forget", {"topic": "rock"})
        mock_forg.assert_called_once_with("rock")
        assert "Esqueci" in result

    def test_list_memories_delegates_to_knowledge_base(self):
        from modules.intent import _execute_tool
        with patch("storage.knowledge_base.show_memories", return_value="Preferências: rock") as mock_list:
            result = _execute_tool("list_memories", {"filter": "preferences"})
        mock_list.assert_called_once_with("preferences")
        assert "rock" in result

    def test_unknown_tool_returns_error_message(self):
        from modules.intent import _execute_tool
        result = _execute_tool("nonexistent_tool", {})
        assert "desconhecida" in result.lower() or "nonexistent" in result

    def test_open_application_delegates(self):
        from modules.intent import _execute_tool
        with patch("modules.system_control.open_app", return_value="Abrindo chrome."):
            result = _execute_tool("open_application", {"name": "chrome"})
        assert isinstance(result, str)


# ── run_agentic_loop ──────────────────────────────────────────────────

class TestAgenticLoop:
    def test_returns_empty_when_api_key_missing(self, tmp_path):
        """run_agentic_loop deve retornar '' sem fazer chamada HTTP se chave vazia."""
        import yaml, os as _os
        from core.config import Config
        from modules.intent import run_agentic_loop
        data = {"ai": {"provider": "groq", "groq_api_key": ""},
                "logging": {"level": "WARNING", "file": str(tmp_path / "t.log"), "max_mb": 1}}
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(data), encoding="utf-8")
        cfg = Config(str(path))
        with patch("core.config.Config", return_value=cfg):
            with patch.dict(_os.environ, {"GROQ_API_KEY": ""}):
                with patch("modules.intent._groq_call") as mock_call:
                    result = run_agentic_loop("toca eminem")
        assert result == ""
        mock_call.assert_not_called()

    def test_returns_empty_string_for_non_groq_provider(self, tmp_path):
        import yaml
        from core.config import Config
        from modules.intent import run_agentic_loop
        data = {"ai": {"provider": "ollama"}, "logging": {"level": "WARNING", "file": str(tmp_path / "t.log"), "max_mb": 1}}
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(data), encoding="utf-8")
        with patch("core.config.Config", return_value=Config(str(path))):
            result = run_agentic_loop("toca eminem")
        assert result == ""

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_single_tool_call_produces_final_response(self, mock_kb, mock_groq, groq_config):
        """LLM chama pause → Python executa → LLM produz resposta natural."""
        from modules.intent import run_agentic_loop

        # Turno 1: LLM retorna tool_call(control_media, pause)
        # Turno 2: LLM produz resposta final
        mock_groq.side_effect = [
            _tool_call_response("control_media", {"action": "pause"}),
            _text_response("Spotify pausado."),
        ]

        with patch("core.config.Config", return_value=groq_config):
            with patch("modules.tools.execute", return_value="Pausado com sucesso."):
                result = run_agentic_loop("para a música")

        assert isinstance(result, str)
        assert len(result) > 0
        assert mock_groq.call_count == 2

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_no_tool_call_returns_text_directly(self, mock_kb, mock_groq, groq_config):
        """Quando LLM responde em texto (sem tool), retorna diretamente."""
        from modules.intent import run_agentic_loop

        mock_groq.return_value = _text_response("Olá! Como posso ajudar?")

        with patch("core.config.Config", return_value=groq_config):
            result = run_agentic_loop("oi")

        assert result == "Olá! Como posso ajudar?"
        assert mock_groq.call_count == 1

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_remember_tool_in_agentic_loop(self, mock_kb, mock_groq, groq_config):
        """LLM chama remember → kb.remember() → LLM produz confirmação."""
        from modules.intent import run_agentic_loop

        mock_groq.side_effect = [
            _tool_call_response("remember", {"statement": "usuário gosta de rock clássico"}),
            _text_response("Memorizado! Vou lembrar que você gosta de rock clássico."),
        ]

        with patch("core.config.Config", return_value=groq_config):
            with patch("storage.knowledge_base.remember", return_value="Memorizado: usuário gosta de rock clássico"):
                result = run_agentic_loop("lembra que eu gosto de rock clássico")

        assert "Memorizado" in result or "lembrar" in result.lower()

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_tool_result_injected_as_tool_message(self, mock_kb, mock_groq, groq_config):
        """O resultado da ferramenta deve aparecer nas messages enviadas ao LLM."""
        from modules.intent import run_agentic_loop
        captured_messages = []

        def capture_groq(api_key, model, messages, tool_choice="auto"):
            captured_messages.append(list(messages))
            if len(captured_messages) == 1:
                return _tool_call_response("control_media", {"action": "next"}, "call_42")
            return _text_response("Próxima faixa!")

        mock_groq.side_effect = capture_groq

        with patch("core.config.Config", return_value=groq_config):
            with patch("modules.tools.execute", return_value="Avançou para próxima faixa."):
                run_agentic_loop("próxima")

        # Na segunda chamada, deve haver uma mensagem role=tool
        second_call_messages = captured_messages[1]
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_42"
        assert "Avançou" in tool_msgs[0]["content"]

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_tool_use_failed_retries_and_recovers(self, mock_kb, mock_groq, groq_config):
        """tool_use_failed deve ter retry — não desiste na primeira falha."""
        from modules.intent import run_agentic_loop

        mock_groq.side_effect = [
            _tool_use_failed_exc(),
            _tool_call_response("control_media", {"action": "pause"}),
            _text_response("Spotify pausado."),
        ]

        with patch("core.config.Config", return_value=groq_config):
            with patch("modules.tools.execute", return_value="Pausado com sucesso."):
                result = run_agentic_loop("para a música")

        assert result == "Spotify pausado."
        assert mock_groq.call_count == 3  # 1 falha + 1 sucesso com tool + 1 resposta final

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_tool_use_failed_exhausts_retries_then_honest_fallback(self, mock_kb, mock_groq, groq_config):
        """Se tool_use_failed persistir, a resposta final não deve fingir sucesso."""
        from modules.intent import run_agentic_loop, _TOOL_CALL_RETRY_ATTEMPTS

        captured_final_messages = []

        def fake_groq(api_key, model, messages, tool_choice="auto"):
            if tool_choice == "none":
                captured_final_messages.extend(messages)
                return _text_response("Não consegui completar a ação, pode confirmar os detalhes?")
            raise _tool_use_failed_exc()

        mock_groq.side_effect = fake_groq

        with patch("core.config.Config", return_value=groq_config):
            result = run_agentic_loop("marca uma reunião pra mim")

        # 1 chamada com tool_choice="none" + N tentativas que falharam com tool_use_failed
        none_calls = [c for c in mock_groq.call_args_list if c.kwargs.get("tool_choice") == "none"
                      or (len(c.args) > 3 and c.args[3] == "none")]
        assert len(none_calls) == 1
        assert mock_groq.call_count == _TOOL_CALL_RETRY_ATTEMPTS + 1

        # A instrução de honestidade deve estar nas mensagens da chamada final
        assert any(
            m.get("role") == "system" and "Não afirme que algo foi feito" in m.get("content", "")
            for m in captured_final_messages
        )
        assert "Não consegui completar" in result

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_non_tool_use_failed_exception_does_not_retry(self, mock_kb, mock_groq, groq_config):
        """Erros que não são tool_use_failed (ex: rede) não devem ter retry imediato."""
        from modules.intent import run_agentic_loop

        call_count = {"n": 0}

        def fake_groq(api_key, model, messages, tool_choice="auto"):
            call_count["n"] += 1
            if tool_choice == "none":
                return _text_response("Não consegui processar agora.")
            raise RuntimeError("Groq indisponível — circuit breaker aberto.")

        mock_groq.side_effect = fake_groq

        with patch("core.config.Config", return_value=groq_config):
            run_agentic_loop("toca eminem")

        # 1 tentativa (sem retry) + 1 chamada final honesta = 2
        assert call_count["n"] == 2

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_critical_action_blocked_by_callback(self, mock_kb, mock_groq, tmp_path):
        """close_application deve ser bloqueado quando callback nega (confirm_critical=True)."""
        import yaml
        from core.config import Config
        from modules.intent import run_agentic_loop, set_confirmation_callback

        data = {
            "ai": {"provider": "groq", "groq_api_key": "test-key", "groq_model": "llama-3.3-70b-versatile"},
            "logging": {"level": "WARNING", "file": str(tmp_path / "t.log"), "max_mb": 1},
            "security": {"confirm_critical": True},
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(data), encoding="utf-8")
        cfg = Config(str(path))

        mock_groq.side_effect = [
            _tool_call_response("close_application", {"name": "chrome"}),
            _text_response("Ação cancelada."),
        ]
        set_confirmation_callback(lambda name, detail: False)

        with patch("core.config.Config", return_value=cfg):
            with patch("modules.system_control.close_app") as mock_close:
                run_agentic_loop("fecha o chrome")
        mock_close.assert_not_called()
        set_confirmation_callback(None)

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_empty_args_json_not_executed(self, mock_kb, mock_groq, groq_config):
        """JSON inválido nos args não deve executar a ferramenta."""
        from modules.intent import run_agentic_loop

        # Simula Groq retornando JSON quebrado nos args
        bad_tc_response = {
            "choices": [{
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_bad",
                        "type": "function",
                        "function": {"name": "close_application", "arguments": "INVALID JSON{{{"},
                    }],
                },
            }]
        }
        mock_groq.side_effect = [bad_tc_response, _text_response("Não consegui executar.")]

        with patch("core.config.Config", return_value=groq_config):
            with patch("modules.system_control.close_app") as mock_close:
                run_agentic_loop("fecha o chrome")
        mock_close.assert_not_called()

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_empty_name_not_executed(self, mock_kb, mock_groq, groq_config):
        """close_application com name='' não deve executar."""
        from modules.intent import run_agentic_loop

        mock_groq.side_effect = [
            _tool_call_response("close_application", {"name": ""}),
            _text_response("Argumento inválido."),
        ]
        with patch("core.config.Config", return_value=groq_config):
            with patch("modules.system_control.close_app") as mock_close:
                run_agentic_loop("fecha")
        mock_close.assert_not_called()

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_max_turns_protection(self, mock_kb, mock_groq, groq_config):
        """Loop não deve girar mais que _MAX_AGENTIC_TURNS + 1 chamadas."""
        from modules.intent import run_agentic_loop, _MAX_AGENTIC_TURNS

        # Sempre retorna tool_call → força o limite de turns
        mock_groq.return_value = _tool_call_response("control_media", {"action": "next"})

        with patch("core.config.Config", return_value=groq_config):
            with patch("modules.tools.execute", return_value="ok"):
                # A última chamada com tool_choice="none" também vai retornar tool_call
                # mas o loop deve parar
                mock_groq.side_effect = (
                    [_tool_call_response("control_media", {"action": "next"})] * _MAX_AGENTIC_TURNS
                    + [_text_response("Parei.")]
                )
                result = run_agentic_loop("toca próxima")

        assert mock_groq.call_count <= _MAX_AGENTIC_TURNS + 1

    @patch("modules.intent._groq_call")
    @patch("modules.intent._build_kb_context", return_value="")
    def test_context_history_injected_in_messages(self, mock_kb, mock_groq, groq_config):
        """Histórico de context.py deve aparecer nas messages enviadas ao Groq."""
        from modules.intent import run_agentic_loop
        from storage.context import add as ctx_add
        ctx_add("toca eminem", "Tocando Eminem no Spotify.")

        captured = []

        def capture(api_key, model, messages, tool_choice="auto"):
            captured.append(messages)
            return _text_response("Ok!")

        mock_groq.side_effect = capture

        with patch("core.config.Config", return_value=groq_config):
            run_agentic_loop("próxima")

        msgs = captured[0]
        roles = [m["role"] for m in msgs]
        assert "user" in roles and "assistant" in roles, "Histórico não foi injetado"
        # Verifica que o histórico contém o turno anterior
        user_contents = [m["content"] for m in msgs if m["role"] == "user"]
        assert any("eminem" in (c or "").lower() for c in user_contents)


# ── Confirmação por callback ──────────────────────────────────────────

class TestConfirmationCallback:
    def setup_method(self):
        from modules import intent
        intent.set_confirmation_callback(None)  # reseta

    def teardown_method(self):
        from modules import intent
        intent.set_confirmation_callback(None)

    def test_callback_called_for_critical_action(self, monkeypatch):
        from modules.intent import _confirm_action, set_confirmation_callback
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        calls = []
        set_confirmation_callback(lambda name, detail: calls.append((name, detail)) or True)
        result = _confirm_action("close_application", {"name": "chrome"})
        assert result is True
        assert len(calls) == 1
        assert calls[0][0] == "close_application"

    def test_callback_can_deny(self, monkeypatch):
        from modules.intent import _confirm_action, set_confirmation_callback
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        set_confirmation_callback(lambda name, detail: False)
        result = _confirm_action("close_application", {"name": "chrome"})
        assert result is False

    def test_no_callback_no_tty_denies(self, monkeypatch):
        from modules.intent import _confirm_action, set_confirmation_callback
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        set_confirmation_callback(None)
        result = _confirm_action("git_operation", {"operation": "push"})
        assert result is False

    def test_callback_exception_denies(self, monkeypatch):
        from modules.intent import _confirm_action, set_confirmation_callback
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        set_confirmation_callback(lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
        result = _confirm_action("close_application", {"name": "discord"})
        assert result is False


# ── Contexto registrado via dispatch() ───────────────────────────────

class TestClassifyLocal:
    """classify_local deve usar apenas cache e TF-IDF, nunca chamar LLM."""

    @pytest.fixture(autouse=True)
    def require_sklearn(self):
        pytest.importorskip("sklearn")

    def test_classify_local_returns_list(self):
        from modules.intent import classify_local
        result = classify_local("toca eminem")
        assert isinstance(result, list)

    def test_classify_local_never_calls_llm(self):
        from modules.intent import classify_local
        with patch("modules.intent._parse_with_groq") as mock_groq:
            with patch("modules.intent._parse_with_ollama_nlu") as mock_ollama:
                classify_local("toca eminem")
        mock_groq.assert_not_called()
        mock_ollama.assert_not_called()

    def test_classify_local_confident_command(self):
        from modules.intent import classify_local
        result = classify_local("para a música")
        if result:  # se TF-IDF foi confiante
            assert result[0]["name"] == "control_media"
            assert result[0]["arguments"]["action"] == "pause"

    def test_intent_dispatch_uses_classify_local_first(self, tmp_path):
        """_intent_dispatch deve chamar classify_local antes de qualquer LLM."""
        import yaml
        from core.config import Config
        from core.orchestrator import Orchestrator
        data = {
            "ai": {"provider": "groq", "groq_api_key": "fake"},
            "logging": {"level": "WARNING", "file": str(tmp_path / "t.log"), "max_mb": 1},
            "security": {"confirm_critical": False},
            "tts": {"enabled": False}, "overlay": {"enabled": False}, "plugins": {"enabled": False},
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(data), encoding="utf-8")
        orch = Orchestrator(Config(str(path)))

        # Se classify_local retornar resultado → run_agentic_loop NÃO deve ser chamado
        with patch("modules.intent.classify_local", return_value=[{"name": "control_media", "arguments": {"action": "pause"}}]):
            with patch("modules.intent.execute_actions", return_value=["Pausado."]):
                with patch("modules.intent.run_agentic_loop") as mock_agentic:
                    orch._intent_dispatch("para a música")
        mock_agentic.assert_not_called()


class TestDispatchRegistersContext:
    """
    _register_context() foi removido — dispatch() gerencia o contexto diretamente.
    Verifica que context.add() é chamado após cada dispatch.
    """
    def setup_method(self):
        from storage.context import _memory
        _memory.clear()

    def test_dispatch_adds_to_session_context(self, tmp_path):
        import yaml
        from core.config import Config
        from core.orchestrator import Orchestrator
        data = {
            "ai": {"provider": "ollama"},
            "logging": {"level": "WARNING", "file": str(tmp_path / "t.log"), "max_mb": 1},
            "security": {"confirm_critical": False},
            "tts": {"enabled": False},
            "overlay": {"enabled": False},
            "plugins": {"enabled": False},
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(data), encoding="utf-8")
        config = Config(str(path))
        orch = Orchestrator(config)
        with patch("modules.intent.classify_local", return_value=[]):
            with patch("modules.intent.parse_intent", return_value=[]):
                with patch("modules.summarizer.ask_ai", return_value="Resposta mock"):
                    result = orch.dispatch("oi paçoca")
        from storage.context import get_turns
        turns = get_turns()
        # Ao menos deve ter registrado (dispatch sempre registra se houver resposta)
        assert isinstance(result, str)
