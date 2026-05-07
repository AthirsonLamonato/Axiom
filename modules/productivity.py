"""
modules/productivity.py — Monitoramento de uso de aplicativos
Rastreia tempo ativo por processo e gera relatórios.
"""

import logging
import time
import threading
from collections import defaultdict
from datetime import datetime, date

logger = logging.getLogger(__name__)

_tracker: "UsageTracker | None" = None


class UsageTracker:
    def __init__(self, interval: int = 10):
        """interval: segundos entre cada amostragem."""
        self.interval = interval
        self._usage: dict[str, float] = defaultdict(float)  # app → segundos
        self._running = False
        self._thread: threading.Thread | None = None
        self._date = date.today()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("UsageTracker iniciado")

    def stop(self):
        self._running = False

    def _loop(self):
        import psutil

        while self._running:
            # Reseta ao virar o dia
            if date.today() != self._date:
                self._usage.clear()
                self._date = date.today()

            try:
                for proc in psutil.process_iter(["name", "status", "cpu_percent"]):
                    if proc.info["status"] == psutil.STATUS_RUNNING:
                        name = proc.info["name"]
                        self._usage[name] += self.interval
            except Exception:
                pass

            time.sleep(self.interval)

    def top_apps(self, n: int = 8) -> list[tuple[str, float]]:
        return sorted(self._usage.items(), key=lambda x: x[1], reverse=True)[:n]

    def summary(self) -> str:
        tops = self.top_apps()
        if not tops:
            return "Nenhum dado de uso disponível ainda."
        lines = [f"Uso de apps — {self._date.strftime('%d/%m/%Y')}:"]
        for name, secs in tops:
            h, m = divmod(int(secs) // 60, 60)
            label = f"{h}h {m:02d}m" if h else f"{m}m"
            lines.append(f"  {name:<30} {label}")
        return "\n".join(lines)


# ── Interface pública ──────────────────────────────────────────────────

def start_tracking():
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
        _tracker.start()


def show_usage(*_) -> str:
    if _tracker is None:
        return "Monitoramento não iniciado. Reinicie o Axiom para ativar."
    return _tracker.summary()


def report(*_) -> str:
    """Gera e salva um relatório de produtividade."""
    if _tracker is None:
        return "Nenhum dado disponível."
    text = _tracker.summary()
    from storage.file_store import save_text
    path = save_text(text, prefix="productivity", ext="txt")
    return f"Relatório salvo em {path}.\n\n{text}"
