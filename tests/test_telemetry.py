"""
tests/test_telemetry.py — Testes para core/telemetry.py

Verifica que:
  - record_command persiste e get_recent retorna os dados
  - get_summary calcula avg_latency_ms corretamente
  - avg_latency_ms de LLM é calculado corretamente (não é sempre zero)
  - fallback_rate reflete chamadas com fallback_used=True
"""

import time
import pytest
from core import telemetry


def _clear_logs():
    with telemetry._lock:
        telemetry._command_log.clear()
        telemetry._llm_log.clear()


def test_record_command_appears_in_recent():
    _clear_logs()
    telemetry.record_command("teste comando", route="modules.test:fn", provider="groq",
                             latency_s=0.5, success=True)
    recent = telemetry.get_recent(5)
    assert len(recent) == 1
    assert recent[0]["route"] == "modules.test:fn"
    assert recent[0]["provider"] == "groq"
    assert recent[0]["latency_ms"] == pytest.approx(500.0, abs=1)


def test_get_summary_correct_avg_latency():
    _clear_logs()
    telemetry.record_command("a", latency_s=0.1, success=True)
    telemetry.record_command("b", latency_s=0.3, success=True)
    summary = telemetry.get_summary()
    assert summary["total_commands"] == 2
    assert abs(summary["avg_latency_ms"] - 200.0) < 1.0


def test_get_summary_success_rate():
    _clear_logs()
    telemetry.record_command("ok1", success=True)
    telemetry.record_command("ok2", success=True)
    telemetry.record_command("fail", success=False)
    summary = telemetry.get_summary()
    assert abs(summary["success_rate"] - (2/3)) < 0.01


def test_get_summary_fallback_rate():
    _clear_logs()
    telemetry.record_command("cmd1", fallback_used=True, success=True)
    telemetry.record_command("cmd2", fallback_used=False, success=True)
    summary = telemetry.get_summary()
    assert abs(summary["fallback_rate"] - 0.5) < 0.01


def test_llm_avg_latency_not_zero():
    _clear_logs()
    # get_summary() retorna cedo se não há comandos — adiciona um dummy
    telemetry.record_command("dummy", success=True)
    telemetry.record_llm_call("groq", latency_s=0.4, prompt_tokens=10, completion_tokens=5)
    telemetry.record_llm_call("groq", latency_s=0.6, prompt_tokens=8, completion_tokens=4)
    summary = telemetry.get_summary()
    groq_stats = summary.get("llm", {}).get("groq", {})
    assert groq_stats.get("calls") == 2
    assert groq_stats.get("total_tokens") == 27
    # avg_latency_ms deve ser (400 + 600) / 2 = 500ms
    assert abs(groq_stats.get("avg_latency_ms", 0) - 500.0) < 1.0


def test_get_summary_empty():
    _clear_logs()
    summary = telemetry.get_summary()
    assert summary == {"total_commands": 0}


def test_get_recent_returns_newest_first():
    _clear_logs()
    telemetry.record_command("first", route="r1", success=True)
    time.sleep(0.01)
    telemetry.record_command("second", route="r2", success=True)
    recent = telemetry.get_recent(5)
    # get_recent retorna em ordem decrescente de timestamp (mais recente primeiro)
    assert recent[0]["route"] == "r2"
    assert recent[1]["route"] == "r1"


def test_providers_counted_correctly():
    _clear_logs()
    telemetry.record_command("a", provider="groq")
    telemetry.record_command("b", provider="groq")
    telemetry.record_command("c", provider="local")
    summary = telemetry.get_summary()
    assert summary["providers"]["groq"] == 2
    assert summary["providers"]["local"] == 1




def test_error_sanitization_removes_credentials():
    value = "request failed Bearer super-secret token=abc123 api_key=xyz789"
    safe = telemetry._sanitize_error(value)
    assert "super-secret" not in safe
    assert "abc123" not in safe
    assert "xyz789" not in safe
    assert "***" in safe
