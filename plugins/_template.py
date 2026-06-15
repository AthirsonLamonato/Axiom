"""
plugins/_template.py — Template para criar novos plugins do Paçoca

Copie este arquivo para plugins/meu_plugin.py e ajuste conforme necessário.
Regras:
  - Funções públicas DEVEM retornar str
  - Use lazy imports para não quebrar o boot se uma dep estiver ausente
  - Cada entrada de ROUTES: (regex, "plugins.meu_plugin:funcao", requer_confirmacao)
  - Arquivos começando com _ são ignorados pelo plugin_loader
"""

# ── Metadados (obrigatórios) ───────────────────────────────────────────
NAME        = "template"
VERSION     = "1.0.0"
DESCRIPTION = "Descrição breve do que este plugin faz"

# ── Rotas (obrigatório) ────────────────────────────────────────────────
# Mesmo formato de ROUTES em core/orchestrator.py:
#   (padrão_regex, "plugins.<modulo>:<funcao>", requer_confirmacao)
ROUTES = [
    (r"exemplo\s+(.+)", "plugins._template:exemplo", False),
]


# ── Handlers ───────────────────────────────────────────────────────────

def exemplo(arg: str, *_) -> str:
    """Exemplo de handler: recebe o grupo capturado pelo regex e retorna str."""
    return f"Template recebeu: {arg}"
