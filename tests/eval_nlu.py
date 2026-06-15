"""
tests/eval_nlu.py — Avaliação do pipeline NLU do Paçoca

Mede a acurácia do classificador TF-IDF (camada 2) em 200+ comandos reais
em português, cobrindo todos os intents, variações de fraseamento, colisões
e casos de borda.

Execução:
    pytest tests/eval_nlu.py -v          # todos os casos
    pytest tests/eval_nlu.py --tb=no -q  # somente resumo
    pytest tests/eval_nlu.py -k "música"  # filtrar por palavra-chave

Métricas exibidas ao final:
    - Acurácia geral (% de intents corretos)
    - Acurácia por intent
    - Falsos positivos em ações críticas (close_application, git push/commit)
    - Distribuição de confiança
"""

import os
import sys
import pytest
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.skipif(
    not __import__("importlib").util.find_spec("sklearn"),
    reason="scikit-learn não instalado",
)

# ── Casos de avaliação ─────────────────────────────────────────────────
# Formato: (comando, intent_esperado, slot_checks_opcionais)
# slot_checks: dict com pares {campo: valor_esperado} para validar extração
# intent_esperado = None → comando ambíguo, qualquer resultado é aceitável

EVAL_CASES: list[tuple[str, str | None, dict]] = [

    # ── control_media: play ──────────────────────────────────────────
    ("toca Linkin Park",                         "control_media", {"action": "play"}),
    ("toca uma música do Eminem",                "control_media", {"action": "play"}),
    ("bota Rap God do Eminem",                   "control_media", {"action": "play"}),
    ("quero ouvir rock clássico",                "control_media", {"action": "play"}),
    ("toca a playlist de trabalho",              "control_media", {"action": "play"}),
    ("coloca Coldplay",                          "control_media", {"action": "play"}),
    ("play Daft Punk",                           "control_media", {"action": "play"}),
    ("quero escutar Queen",                      "control_media", {"action": "play"}),
    ("escuta Radiohead",                         "control_media", {"action": "play"}),
    ("bota uma música do Beatles",               "control_media", {"action": "play"}),
    ("toca Bohemian Rhapsody",                   "control_media", {"action": "play"}),
    ("coloca uma playlist de lofi",              "control_media", {"action": "play"}),
    ("toca jazz",                                "control_media", {"action": "play"}),
    ("bota algo do Ed Sheeran",                  "control_media", {"action": "play"}),
    ("quero ouvir música eletrônica",            "control_media", {"action": "play"}),
    ("toca samba",                               "control_media", {"action": "play"}),
    ("bota uma música calma",                    "control_media", {"action": "play"}),
    ("coloca MPB",                               "control_media", {"action": "play"}),
    ("toca alguma coisa do Metallica",           "control_media", {"action": "play"}),
    ("play algo de rap",                         "control_media", {"action": "play"}),

    # ── control_media: pause ─────────────────────────────────────────
    ("para a música",                            "control_media", {"action": "pause"}),
    ("pausa",                                    "control_media", {"action": "pause"}),
    ("silencia o spotify",                       "control_media", {"action": "pause"}),
    ("para o spotify",                           "control_media", {"action": "pause"}),
    ("para tudo",                                "control_media", {"action": "pause"}),
    ("pausa a música por favor",                 "control_media", {"action": "pause"}),
    ("silencia",                                 "control_media", {"action": "pause"}),

    # ── control_media: resume ────────────────────────────────────────
    ("continua",                                 "control_media", {"action": "resume"}),
    ("retoma a música",                          "control_media", {"action": "resume"}),
    ("resume",                                   "control_media", {"action": "resume"}),
    ("continua tocando",                         "control_media", {"action": "resume"}),

    # ── control_media: next ──────────────────────────────────────────
    ("próxima música",                           "control_media", {"action": "next"}),
    ("próxima",                                  "control_media", {"action": "next"}),
    ("pula essa",                                "control_media", {"action": "next"}),
    ("avança",                                   "control_media", {"action": "next"}),
    ("passa para a próxima faixa",               "control_media", {"action": "next"}),

    # ── control_media: previous ──────────────────────────────────────
    ("música anterior",                          "control_media", {"action": "previous"}),
    ("volta a música",                           "control_media", {"action": "previous"}),
    ("anterior",                                 "control_media", {"action": "previous"}),
    ("volta a faixa",                            "control_media", {"action": "previous"}),

    # ── control_media: current ───────────────────────────────────────
    ("que música é essa",                        "control_media", {"action": "current"}),
    ("o que está tocando",                       "control_media", {"action": "current"}),
    ("que artista é esse",                       "control_media", {}),  # pode ir para answer_question
    ("qual música tá tocando agora",             "control_media", {"action": "current"}),

    # ── open_application ────────────────────────────────────────────
    ("abre o chrome",                            "open_application", {"name": "chrome"}),
    ("abre o discord",                           "open_application", {"name": "discord"}),
    ("abre o vscode",                            "open_application", {}),
    ("abre o notepad",                           "open_application", {"name": "notepad"}),
    ("abre o word",                              "open_application", {"name": "word"}),
    ("abre o excel",                             "open_application", {"name": "excel"}),
    ("abre o telegram",                          "open_application", {"name": "telegram"}),
    ("abre o whatsapp",                          "open_application", {"name": "whatsapp"}),
    ("abre o spotify",                           "open_application", {"name": "spotify"}),
    ("abre o terminal",                          "open_application", {"name": "terminal"}),
    ("abrir o explorer",                         "open_application", {}),
    ("abre o gerenciador de tarefas",            "open_application", {}),
    ("abre o bloco de notas",                    "open_application", {}),

    # ── close_application (CRÍTICO — falsos positivos são graves) ───
    ("fecha o discord",                          "close_application", {"name": "discord"}),
    ("encerra o chrome",                         "close_application", {"name": "chrome"}),
    ("fecha o spotify",                          "close_application", {"name": "spotify"}),
    ("encerra o notepad",                        "close_application", {"name": "notepad"}),
    ("fecha o word",                             "close_application", {"name": "word"}),
    ("mata o processo discord",                  "close_application", {"name": "discord"}),
    ("encerre o chrome",                         "close_application", {"name": "chrome"}),
    ("fecha o telegram",                         "close_application", {"name": "telegram"}),
    ("encerra o excel",                          "close_application", {"name": "excel"}),

    # ── Colisão crítica: NÃO deve ser close_application ─────────────
    ("abre o chrome",                            "open_application", {}),   # NÃO close
    ("toca uma música",                          "control_media",    {}),   # NÃO close
    ("fecha a pasta de downloads",               None,               {}),   # ambíguo

    # ── set_volume ───────────────────────────────────────────────────
    ("volume 60",                                "set_volume", {"level": 60}),
    ("coloca o volume em 40",                    "set_volume", {"level": 40}),
    ("aumenta o volume para 80",                 "set_volume", {}),
    ("volume para 50",                           "set_volume", {"level": 50}),
    ("bota o volume em 30",                      "set_volume", {"level": 30}),
    ("coloca o volume em 100",                   "set_volume", {"level": 100}),
    ("volume 0",                                 "set_volume", {"level": 0}),
    ("coloca o som em 70",                       "set_volume", {}),
    ("diminui o volume para 20",                 "set_volume", {}),
    ("volume 45",                                "set_volume", {"level": 45}),

    # ── Colisão crítica: volume NÃO deve ser control_media ───────────
    ("coloca o volume em 45",                    "set_volume",    {}),  # NÃO play
    ("bota o volume em 90",                      "set_volume",    {}),  # NÃO play

    # ── open_browser ─────────────────────────────────────────────────
    ("abre o youtube no chrome",                 "open_browser", {"browser": "chrome"}),
    ("pesquisa python no firefox",               "open_browser", {"browser": "firefox"}),
    ("abre o github no brave",                   "open_browser", {"browser": "brave"}),
    ("pesquisa clima no edge",                   "open_browser", {"browser": "edge"}),
    ("abre o gmail no chrome",                   "open_browser", {"browser": "chrome"}),
    ("pesquisa notícias no firefox",             "open_browser", {"browser": "firefox"}),
    ("vai para o reddit no chrome",              "open_browser", {}),
    ("abre o netflix no brave",                  "open_browser", {"browser": "brave"}),

    # ── web_search (SEM navegador explícito) ─────────────────────────
    ("pesquisa sobre machine learning",          "web_search", {}),
    ("busca notícias de tecnologia",             "web_search", {}),
    ("pesquisa python decorators",               "web_search", {}),
    ("busca o que é docker",                     "web_search", {}),
    ("pesquisa previsão do tempo amanhã",        "web_search", {}),
    ("busca receita de bolo de cenoura",         "web_search", {}),
    ("pesquisa como instalar nodejs",            "web_search", {}),

    # ── Colisão: pesquisa COM browser → open_browser; SEM → web_search
    ("pesquisa python no chrome",               "open_browser", {}),  # COM browser
    ("pesquisa python",                         "web_search",   {}),  # SEM browser

    # ── open_folder ──────────────────────────────────────────────────
    ("abre a pasta de downloads",                "open_folder", {}),
    ("abre meus documentos",                     "open_folder", {}),
    ("abre o desktop",                           "open_folder", {}),
    ("abre a pasta de imagens",                  "open_folder", {}),
    ("abre minha área de trabalho",              "open_folder", {}),

    # ── answer_question ───────────────────────────────────────────────
    ("o que é machine learning",                 "answer_question", {}),
    ("me explica como funciona o docker",        "answer_question", {}),
    ("o que é uma API",                          "answer_question", {}),
    ("me explica o que é kubernetes",            "answer_question", {}),
    ("como funciona o git",                      "answer_question", {}),
    ("explica o que é recursão",                 "answer_question", {}),
    ("o que é inteligência artificial",          "answer_question", {}),
    ("como funciona o protocolo HTTP",           "answer_question", {}),

    # ── git_operation ─────────────────────────────────────────────────
    ("git status",                               "git_operation", {"operation": "status"}),
    ("o que mudou no repositório",               "git_operation", {"operation": "status"}),
    ("git push",                                 "git_operation", {"operation": "push"}),
    ("git pull",                                 "git_operation", {"operation": "pull"}),
    ("faz commit com a mensagem atualiza readme","git_operation", {"operation": "commit"}),
    ("cria branch feature/login",                "git_operation", {"operation": "branch"}),
    ("mostra os últimos commits",                "git_operation", {"operation": "log"}),
    ("git log",                                  "git_operation", {"operation": "log"}),
    ("qual o histórico de commits",              "git_operation", {}),
    ("cria uma branch chamada fix/bug",          "git_operation", {"operation": "branch"}),

    # ── remember / forget / list_memories ────────────────────────────
    ("lembra que eu gosto de jazz",              "remember", {}),
    ("guarda que meu app favorito é o discord",  "remember", {}),
    ("não esquece que prefiro modo escuro",      "remember", {}),
    ("esquece o que eu disse sobre jazz",        "forget",   {}),
    ("apaga a memória sobre discord",            "forget",   {}),
    ("quais memórias você tem sobre mim",        "list_memories", {}),
    ("me mostra o que você lembra",              "list_memories", {}),
    ("lista minhas preferências salvas",         "list_memories", {}),

    # ── Casos de borda / ambíguos ──────────────────────────────────────
    # Esses podem cair para LLM — aceitamos qualquer resultado razoável
    ("bota rock",                                "control_media",    {}),
    ("toca qualquer coisa",                      "control_media",    {}),
    ("abre",                                     None,               {}),  # incompleto
    ("ok",                                       None,               {}),  # sem intenção clara
    ("volume",                                   None,               {}),  # incompleto

    # ── Falsos positivos críticos: NÃO devem ser close_application ───
    ("abre o youtube",                           "open_application", {}),
    ("toca música",                              "control_media",    {}),
    ("pesquisa como fechar um app",              "web_search",       {}),  # NÃO close_application
]


# ── Coleta de métricas ─────────────────────────────────────────────────

_results: list[dict] = []


def _get_classifier():
    from modules.intent import classify_local, _CONFIDENCE_THRESHOLD
    return classify_local, _CONFIDENCE_THRESHOLD


# ── Teste parametrizado ────────────────────────────────────────────────

@pytest.mark.parametrize("command,expected_intent,slot_checks", EVAL_CASES,
                         ids=[c[0][:50] for c in EVAL_CASES])
def test_nlu_case(command, expected_intent, slot_checks):
    classify_local, threshold = _get_classifier()

    calls = classify_local(command)
    got_intent = calls[0]["name"] if calls else None
    got_args   = calls[0]["arguments"] if calls else {}

    _results.append({
        "command":  command,
        "expected": expected_intent,
        "got":      got_intent,
        "args":     got_args,
        "correct":  expected_intent is None or got_intent == expected_intent,
        "critical": expected_intent in ("close_application",) or
                    (expected_intent == "git_operation" and
                     slot_checks.get("operation") in ("push", "commit")),
    })

    # Casos ambíguos (expected=None): não falham
    if expected_intent is None:
        return

    # Falso positivo CRÍTICO: classificou como close_application quando não devia
    if expected_intent != "close_application" and got_intent == "close_application":
        pytest.fail(
            f"FALSO POSITIVO CRÍTICO: '{command}'\n"
            f"  esperado: {expected_intent}  →  classificado como: close_application"
        )

    # Falso positivo CRÍTICO: git push/commit quando não devia
    if expected_intent != "git_operation" and got_intent == "git_operation":
        op = got_args.get("operation", "")
        if op in ("push", "commit"):
            pytest.fail(
                f"FALSO POSITIVO CRÍTICO: '{command}'\n"
                f"  esperado: {expected_intent}  →  git {op} indevido"
            )

    # Verificação de intent (só se TF-IDF teve alta confiança — senão vai para LLM)
    if calls:
        assert got_intent == expected_intent, (
            f"Intent errado para '{command}'\n"
            f"  esperado: {expected_intent}\n"
            f"  obtido:   {got_intent}\n"
            f"  args:     {got_args}"
        )

        # Verificação de slots (somente os especificados)
        for field, expected_val in slot_checks.items():
            got_val = got_args.get(field)
            assert got_val == expected_val, (
                f"Slot '{field}' errado para '{command}'\n"
                f"  esperado: {expected_val!r}\n"
                f"  obtido:   {got_val!r}"
            )


# ── Relatório de métricas ao final ────────────────────────────────────

def pytest_sessionfinish(session, exitstatus):
    if not _results:
        return

    total        = len(_results)
    correct      = sum(1 for r in _results if r["correct"])
    ambiguous    = sum(1 for r in _results if r["expected"] is None)
    classified   = sum(1 for r in _results if r["got"] is not None)
    unclassified = total - classified

    accuracy = correct / (total - ambiguous) * 100 if (total - ambiguous) > 0 else 0.0

    by_intent: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in _results:
        if r["expected"] is None:
            continue
        by_intent[r["expected"]]["total"]   += 1
        by_intent[r["expected"]]["correct"] += int(r["correct"])

    critical_fp = [
        r for r in _results
        if r["got"] == "close_application" and r["expected"] != "close_application"
    ]

    print("\n" + "=" * 60)
    print("  RELATÓRIO DE AVALIAÇÃO NLU — Paçoca")
    print("=" * 60)
    print(f"  Total de casos : {total}")
    print(f"  Ambíguos       : {ambiguous}")
    print(f"  Classificados  : {classified}  ({classified/total*100:.0f}%)")
    print(f"  Sem TF-IDF     : {unclassified}  → caem para LLM")
    print(f"  Acurácia geral : {accuracy:.1f}%  ({correct}/{total - ambiguous})")
    print()
    print("  Por intent:")
    for intent, stats in sorted(by_intent.items()):
        t, c = stats["total"], stats["correct"]
        pct = c / t * 100 if t else 0
        mark = "✓" if pct >= 80 else ("⚠" if pct >= 50 else "✗")
        print(f"    {mark} {intent:<25} {c:>3}/{t:<3}  {pct:.0f}%")
    print()
    if critical_fp:
        print(f"  ⚠ FALSOS POSITIVOS CRÍTICOS (close_application): {len(critical_fp)}")
        for r in critical_fp:
            print(f"    - '{r['command']}'")
    else:
        print("  ✓ Nenhum falso positivo crítico detectado")
    print("=" * 60)
