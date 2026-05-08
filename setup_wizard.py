"""
setup_wizard.py — Assistente de instalação visual do Axiom
Usa apenas tkinter (stdlib) — funciona sem instalar nada primeiro.
Roda em qualquer PC Windows, mesmo sem Python instalado.
"""

import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ── Paleta ────────────────────────────────────────────────────────────
BG      = "#0d1117"
BG2     = "#161b22"
BG3     = "#21262d"
FG      = "#c9d1d9"
FG2     = "#8b949e"
ACCENT  = "#58a6ff"
GREEN   = "#3fb950"
RED     = "#f85149"
YELLOW  = "#e3b341"
BORDER  = "#30363d"

def _detect_install_dir() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent.resolve()
        # Se rodando de dist/ durante dev build, usa o pai (raiz do projeto)
        if exe_dir.name == "dist" and (exe_dir.parent / "main.py").exists():
            return exe_dir.parent
        return exe_dir
    return Path(__file__).parent.resolve()

INSTALL_DIR = _detect_install_dir()

PACKAGES_REQUIRED = [
    "pyyaml", "psutil", "requests", "duckduckgo-search",
    "schedule", "keyboard", "plyer",
    "faster-whisper", "pyaudio",
    "PyQt6", "pyttsx3",
    "google-auth", "google-auth-oauthlib", "google-api-python-client",
]
PACKAGES_OPTIONAL = [
    ("fastapi", "Dashboard web (recomendado)"),
    ("uvicorn[standard]", "Dashboard web (recomendado)"),
    ("pyperclip", "Clipboard por voz"),
    ("pytesseract", "OCR de tela"),
    ("Pillow", "OCR de tela"),
]

# ── Python discovery ──────────────────────────────────────────────────

_PYTHON_EXE: str = ""   # cache; vazio = ainda não buscou


def _python_version_ok(exe: str) -> bool:
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=5)
        ver = r.stdout.strip() or r.stderr.strip()
        m = re.search(r"Python 3\.(\d+)", ver)
        return bool(m and int(m.group(1)) >= 9)
    except Exception:
        return False


def _find_python() -> str:
    """Retorna o caminho de um Python 3.9+ usável, ou string vazia."""
    global _PYTHON_EXE
    if _PYTHON_EXE:
        return _PYTHON_EXE

    # 1. Se não for exe congelado, o próprio processo já É Python
    if not getattr(sys, "frozen", False):
        if _python_version_ok(sys.executable):
            _PYTHON_EXE = sys.executable
            return _PYTHON_EXE

    # 2. PATH
    for name in ("python3", "python", "py"):
        p = shutil.which(name)
        if p and _python_version_ok(p):
            _PYTHON_EXE = p
            return _PYTHON_EXE

    # 3. Locais comuns no Windows (mais recente primeiro)
    patterns = [
        r"C:\Users\*\AppData\Local\Programs\Python\Python3*\python.exe",
        r"C:\Python3*\python.exe",
        r"C:\Program Files\Python3*\python.exe",
        r"C:\Program Files (x86)\Python3*\python.exe",
    ]
    candidates: list[str] = []
    for pat in patterns:
        candidates.extend(glob.glob(pat))
    for exe in sorted(candidates, reverse=True):
        if _python_version_ok(exe):
            _PYTHON_EXE = exe
            return _PYTHON_EXE

    return ""


def _auto_install_python(on_progress, on_done):
    """Baixa e instala Python 3.12 silenciosamente (sem admin, sem UAC)."""
    arch = "amd64" if platform.machine().endswith("64") else "win32"
    version = "3.12.9"
    url = f"https://www.python.org/ftp/python/{version}/python-{version}-{arch}.exe"
    tmp = Path(os.environ.get("TEMP", str(Path.home()))) / f"python-{version}-installer.exe"

    def run():
        global _PYTHON_EXE
        try:
            # Download com progresso
            def reporthook(count, block, total):
                if total > 0:
                    mb_done = count * block / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    pct = min(45, int(count * block / total * 45))
                    on_progress(f"Baixando Python {version}… {mb_done:.1f}/{mb_total:.0f} MB", pct)

            on_progress(f"Conectando a python.org…", 2)
            urllib.request.urlretrieve(url, str(tmp), reporthook)

            on_progress("Instalando Python… (pode demorar 1-2 min)", 50)
            subprocess.run(
                [str(tmp), "/quiet", "InstallAllUsers=0",
                 "PrependPath=1", "Include_pip=1", "Include_launcher=0"],
                check=True, timeout=300,
            )
            _PYTHON_EXE = ""   # força re-busca
            found = _find_python()
            if found:
                on_progress(f"Python instalado: {found}", 100)
                on_done(True, "")
            else:
                on_done(False, "Instalação concluída mas Python não foi encontrado. Reinicie o wizard.")
        except Exception as e:
            on_done(False, str(e))

    threading.Thread(target=run, daemon=True).start()


# ── Utilitários ───────────────────────────────────────────────────────

def pip_install(pkg: str, callback=None) -> bool:
    exe = _find_python()
    if not exe:
        if callback:
            callback(pkg, False)
        return False
    result = subprocess.run(
        [exe, "-m", "pip", "install", pkg, "--quiet"],
        capture_output=True, text=True,
    )
    ok = result.returncode == 0
    if callback:
        callback(pkg, ok)
    return ok


def pkg_installed(name: str) -> bool:
    exe = _find_python()
    if not exe:
        return False
    clean = name.split("[")[0].replace("-", "_")
    r = subprocess.run([exe, "-c", f"import {clean}"],
                       capture_output=True, timeout=5)
    return r.returncode == 0


def ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def ollama_model_exists(model="llama3") -> bool:
    if not ollama_installed():
        return False
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    return model in result.stdout


def read_config() -> dict:
    cfg_path = INSTALL_DIR / "core" / "config.yaml"
    try:
        exe = _find_python()
        if exe:
            r = subprocess.run([exe, "-c",
                "import yaml, sys; print(__import__('json').dumps(yaml.safe_load(open(sys.argv[1]))))",
                str(cfg_path)], capture_output=True, text=True)
            if r.returncode == 0:
                return json.loads(r.stdout)
    except Exception:
        pass
    return {}


def write_config_values(values: dict):
    cfg_path = INSTALL_DIR / "core" / "config.yaml"
    exe = _find_python()
    if not exe:
        return "Python não encontrado — não é possível salvar config."
    script = (
        "import yaml, json, sys\n"
        "p = sys.argv[1]\n"
        "v = json.loads(sys.argv[2])\n"
        "d = yaml.safe_load(open(p)) or {}\n"
        "[(d.update({s: {**d.get(s,{}), **sv}}) if isinstance(d.get(s), dict) else d.update({s: sv})) for s, sv in v.items()]\n"
        "yaml.dump(d, open(p,'w',encoding='utf-8'), allow_unicode=True, default_flow_style=False)\n"
    )
    try:
        r = subprocess.run([exe, "-c", script, str(cfg_path), json.dumps(values)],
                           capture_output=True, text=True)
        return True if r.returncode == 0 else r.stderr.strip()
    except Exception as e:
        return str(e)


def create_shortcut():
    if platform.system() != "Windows":
        return
    desktop = Path.home() / "Desktop"
    python_exe = _find_python() or "python"
    bat = desktop / "Axiom.bat"
    bat.write_text(
        f'@echo off\ncd /d "{INSTALL_DIR}"\n'
        f'"{python_exe}" main.py\npause\n',
        encoding="utf-8",
    )
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        lnk = shell.CreateShortCut(str(desktop / "Axiom.lnk"))
        lnk.TargetPath = python_exe
        lnk.Arguments = "main.py"
        lnk.WorkingDirectory = str(INSTALL_DIR)
        lnk.Description = "Axiom — Assistente pessoal inteligente"
        lnk.save()
        bat.unlink(missing_ok=True)
    except Exception:
        pass


# ── Widgets reutilizáveis ─────────────────────────────────────────────

def styled_frame(parent, **kw) -> tk.Frame:
    return tk.Frame(parent, bg=BG, **kw)


def h1(parent, text) -> tk.Label:
    return tk.Label(parent, text=text, bg=BG, fg=ACCENT,
                    font=("Segoe UI", 18, "bold"))


def h2(parent, text) -> tk.Label:
    return tk.Label(parent, text=text, bg=BG, fg=FG,
                    font=("Segoe UI", 11, "bold"))


def body(parent, text, color=FG2) -> tk.Label:
    return tk.Label(parent, text=text, bg=BG, fg=color,
                    font=("Segoe UI", 9), wraplength=480, justify="left")


def btn(parent, text, command, color=ACCENT, width=14) -> tk.Button:
    return tk.Button(
        parent, text=text, command=command,
        bg=color, fg="white", activebackground=color,
        relief="flat", padx=10, pady=6,
        font=("Segoe UI", 9), width=width, cursor="hand2",
    )


def status_dot(parent, ok=None) -> tk.Label:
    color = GREEN if ok is True else (RED if ok is False else YELLOW)
    return tk.Label(parent, text="●", bg=BG, fg=color, font=("Segoe UI", 10))


# ── Janela principal ──────────────────────────────────────────────────

class WizardApp(tk.Tk):
    PAGES = ["Boas-vindas", "Dependências", "Ollama & IA",
             "Configuração", "Google", "Concluído"]

    def __init__(self):
        super().__init__()
        self.title("Axiom — Assistente de instalação")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("540x580")
        self._center()

        self._page_idx = 0
        self._frames: list[tk.Frame] = []
        self._build_chrome()
        self._build_pages()
        self._show_page(0)

    def _center(self):
        self.update_idletasks()
        w, h = 540, 580
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Cromo ─────────────────────────────────────────────────────────

    def _build_chrome(self):
        hdr = tk.Frame(self, bg=BG2, height=70)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚡ AXIOM", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 20, "bold")).pack(side="left", padx=20, pady=12)
        self._step_lbl = tk.Label(hdr, text="", bg=BG2, fg=FG2,
                                   font=("Segoe UI", 9))
        self._step_lbl.pack(side="right", padx=20)

        self._progress = ttk.Progressbar(self, length=540, mode="determinate",
                                          maximum=len(self.PAGES) - 1)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=BG3,
                        background=ACCENT, thickness=4)
        self._progress.pack(fill="x")

        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True, padx=24, pady=16)

        nav = tk.Frame(self, bg=BG2, height=52)
        nav.pack(fill="x", side="bottom")
        nav.pack_propagate(False)
        self._btn_back = btn(nav, "← Voltar", self._go_back, color=BG3, width=10)
        self._btn_back.pack(side="left", padx=16, pady=10)
        self._btn_next = btn(nav, "Próximo →", self._go_next, width=12)
        self._btn_next.pack(side="right", padx=16, pady=10)

    def _show_page(self, idx: int):
        for f in self._frames:
            f.pack_forget()
        self._frames[idx].pack(fill="both", expand=True)
        self._page_idx = idx
        self._progress["value"] = idx
        self._step_lbl.config(
            text=f"Etapa {idx + 1} / {len(self.PAGES)}  —  {self.PAGES[idx]}"
        )
        self._btn_back.config(state="normal" if idx > 0 else "disabled")
        last = idx == len(self.PAGES) - 1
        self._btn_next.config(
            text="Fechar" if last else "Próximo →",
            command=self.destroy if last else self._go_next,
        )
        if hasattr(self._frames[idx], "_on_show"):
            self._frames[idx]._on_show()

    def _go_next(self):
        if self._page_idx < len(self.PAGES) - 1:
            self._show_page(self._page_idx + 1)

    def _go_back(self):
        if self._page_idx > 0:
            self._show_page(self._page_idx - 1)

    # ── Páginas ───────────────────────────────────────────────────────

    def _build_pages(self):
        self._frames = [
            self._page_welcome(),
            self._page_deps(),
            self._page_ollama(),
            self._page_config(),
            self._page_google(),
            self._page_finish(),
        ]
        for f in self._frames:
            f.pack(fill="both", expand=True)
            f.pack_forget()

    # ── Página 1 — Boas-vindas ────────────────────────────────────────

    def _page_welcome(self) -> tk.Frame:
        f = styled_frame(self._content)

        h1(f, "Bem-vindo ao Axiom").pack(anchor="w", pady=(0, 4))
        body(f, "Assistente pessoal de desktop — controle por voz ou texto, "
                "100% local e gratuito.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        h2(f, "Verificação do sistema").pack(anchor="w", pady=(0, 8))

        info = tk.Frame(f, bg=BG2, padx=12, pady=10)
        info.pack(fill="x")

        # Sistema e diretório
        for label, ok in [
            (f"Sistema: {platform.system()} {platform.release()} "
             f"({'64-bit' if platform.machine().endswith('64') else '32-bit'})", True),
            (f"Diretório: {INSTALL_DIR}", True),
        ]:
            row = tk.Frame(info, bg=BG2)
            row.pack(fill="x", pady=2)
            status_dot(row, ok).pack(side="left")
            tk.Label(row, text=f"  {label}", bg=BG2, fg=FG,
                     font=("Segoe UI", 9)).pack(side="left")

        # Python — pode não estar instalado
        py_row = tk.Frame(info, bg=BG2)
        py_row.pack(fill="x", pady=2)
        py_found = _find_python()
        self._py_dot = status_dot(py_row, bool(py_found))
        self._py_dot.pack(side="left")
        self._py_lbl = tk.Label(
            py_row,
            text=f"  Python: {py_found}" if py_found else "  Python 3.9+ não encontrado",
            bg=BG2, fg=FG, font=("Segoe UI", 9),
        )
        self._py_lbl.pack(side="left")

        # Painel de instalação automática (visível só se Python ausente)
        self._py_panel = tk.Frame(f, bg=BG3, padx=12, pady=10)
        if not py_found:
            self._py_panel.pack(fill="x", pady=(8, 0))
            tk.Label(self._py_panel,
                     text="Python não encontrado. Instalando automaticamente (sem admin)…",
                     bg=BG3, fg=YELLOW, font=("Segoe UI", 8), wraplength=460,
                     justify="left").pack(anchor="w")
            self._py_prog = ttk.Progressbar(self._py_panel, length=460,
                                             mode="determinate", maximum=100)
            self._py_prog.pack(fill="x", pady=(6, 4))
            self._py_status = tk.Label(self._py_panel, text="", bg=BG3,
                                       fg=FG2, font=("Segoe UI", 8))
            self._py_status.pack(anchor="w")
            btn_row = tk.Frame(self._py_panel, bg=BG3)
            btn_row.pack(anchor="w", pady=(4, 0))
            btn(btn_row, "↺ Reinstalar Python 3.12",
                self._install_python_auto, width=22).pack(side="left")
            btn(btn_row, "Baixar manualmente",
                lambda: webbrowser.open("https://www.python.org/downloads/"),
                color=BG, width=17).pack(side="left", padx=8)
            # Auto-inicia instalação se rodando como exe (sem Python no PC)
            if getattr(sys, "frozen", False):
                self.after(800, self._install_python_auto)

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        body(f, "Este assistente irá:\n"
                "  1. Instalar as dependências Python\n"
                "  2. Configurar o Ollama (IA local)\n"
                "  3. Ajustar suas preferências\n"
                "  4. Fazer login com o Google (Calendar + Drive)\n"
                "  5. Criar um atalho na área de trabalho").pack(anchor="w")
        return f

    def _install_python_auto(self):
        if not hasattr(self, "_py_prog"):
            return

        def on_progress(msg, pct):
            self.after(0, lambda m=msg, p=pct: [
                self._py_status.config(text=m, fg=YELLOW),
                self._py_prog.config(value=p),
            ])

        def on_done(ok, err=""):
            def _update():
                if ok:
                    exe = _find_python()
                    self._py_dot.config(fg=GREEN)
                    self._py_lbl.config(text=f"  Python: {exe}")
                    self._py_status.config(text="Python instalado com sucesso!", fg=GREEN)
                    self._py_prog.config(value=100)
                else:
                    self._py_status.config(text=f"Erro: {err}", fg=RED)
            self.after(0, _update)

        _auto_install_python(on_progress, on_done)

    # ── Página 2 — Dependências ───────────────────────────────────────

    def _page_deps(self) -> tk.Frame:
        f = styled_frame(self._content)
        h1(f, "Dependências Python").pack(anchor="w", pady=(0, 4))
        body(f, "Pacotes necessários para o Axiom funcionar.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        list_frame = tk.Frame(f, bg=BG2)
        list_frame.pack(fill="x")
        self._dep_labels: dict[str, tk.Label] = {}

        canvas = tk.Canvas(list_frame, bg=BG2, highlightthickness=0, height=200)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scroll_f = tk.Frame(canvas, bg=BG2)
        scroll_f.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_f, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        all_pkgs = PACKAGES_REQUIRED + [p for p, _ in PACKAGES_OPTIONAL]
        for pkg in all_pkgs:
            row = tk.Frame(scroll_f, bg=BG2)
            row.pack(fill="x", pady=1, padx=8)
            installed = pkg_installed(pkg)
            dot = status_dot(row, installed)
            dot.pack(side="left")
            lbl_text = f"  {pkg}"
            if any(pkg == p for p, _ in PACKAGES_OPTIONAL):
                opt_desc = next(d for p, d in PACKAGES_OPTIONAL if p == pkg)
                lbl_text += f"  ({opt_desc})"
            tk.Label(row, text=lbl_text, bg=BG2, fg=FG if installed else FG2,
                     font=("Segoe UI", 8)).pack(side="left")
            self._dep_labels[pkg] = dot

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=8)
        self._dep_progress = ttk.Progressbar(f, length=480, mode="determinate",
                                              maximum=len(all_pkgs))
        self._dep_progress.pack(fill="x")
        self._dep_status = tk.Label(f, text="Pronto para instalar.", bg=BG, fg=FG2,
                                     font=("Segoe UI", 8))
        self._dep_status.pack(anchor="w", pady=4)

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w")
        btn(btn_row, "Instalar tudo", self._install_deps, width=14).pack(side="left", pady=4)
        btn(btn_row, "Só opcionais",
            lambda: self._install_deps(optional_only=True),
            color=BG3, width=13).pack(side="left", padx=8)
        return f

    def _install_deps(self, optional_only=False):
        if not _find_python():
            messagebox.showerror("Python não encontrado",
                                 "Instale o Python primeiro (passo 1).")
            return
        pkgs = (
            [p for p, _ in PACKAGES_OPTIONAL] if optional_only
            else PACKAGES_REQUIRED + [p for p, _ in PACKAGES_OPTIONAL]
        )
        self._dep_progress["maximum"] = len(pkgs)
        self._dep_progress["value"] = 0

        def run():
            for i, pkg in enumerate(pkgs, 1):
                self._dep_status.config(text=f"Instalando {pkg}…", fg=YELLOW)
                ok = pip_install(pkg)
                dot = self._dep_labels.get(pkg)
                if dot:
                    dot.config(fg=GREEN if ok else RED)
                self._dep_progress["value"] = i
            self._dep_status.config(text="Concluído.", fg=GREEN)

        threading.Thread(target=run, daemon=True).start()

    # ── Página 3 — Ollama ─────────────────────────────────────────────

    def _page_ollama(self) -> tk.Frame:
        f = styled_frame(self._content)
        h1(f, "Ollama & Modelo de IA").pack(anchor="w", pady=(0, 4))
        body(f, "O Axiom usa o Ollama para rodar um LLM local. "
                "Sem internet após o download.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        status_frame = tk.Frame(f, bg=BG2, padx=12, pady=10)
        status_frame.pack(fill="x")
        self._ollama_dot = status_dot(status_frame, ollama_installed())
        self._ollama_dot.pack(side="left")
        self._ollama_lbl = tk.Label(
            status_frame,
            text=f"  Ollama {'encontrado' if ollama_installed() else 'não encontrado'}",
            bg=BG2, fg=FG, font=("Segoe UI", 9),
        )
        self._ollama_lbl.pack(side="left")

        def refresh_ollama():
            ok = ollama_installed()
            self._ollama_dot.config(fg=GREEN if ok else RED)
            self._ollama_lbl.config(
                text=f"  Ollama {'encontrado' if ok else 'não encontrado'}"
            )

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w", pady=8)
        btn(btn_row, "Baixar Ollama",
            lambda: [webbrowser.open("https://ollama.com/download"), refresh_ollama()],
            width=14).pack(side="left")
        btn(btn_row, "↺ Verificar", refresh_ollama, color=BG3, width=10).pack(side="left", padx=8)

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=8)
        h2(f, "Modelo de linguagem").pack(anchor="w", pady=(0, 6))

        model_frame = tk.Frame(f, bg=BG)
        model_frame.pack(anchor="w")
        tk.Label(model_frame, text="Modelo:", bg=BG, fg=FG,
                 font=("Segoe UI", 9)).pack(side="left")
        self._model_var = tk.StringVar(value="llama3")
        for m in ("llama3", "mistral", "phi3"):
            tk.Radiobutton(model_frame, text=m, variable=self._model_var, value=m,
                           bg=BG, fg=FG, selectcolor=BG2,
                           activebackground=BG, font=("Segoe UI", 9)).pack(side="left", padx=8)

        self._model_progress = ttk.Progressbar(f, length=480, mode="indeterminate")
        self._model_progress.pack(fill="x", pady=8)
        self._model_status = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8))
        self._model_status.pack(anchor="w")
        btn(f, "⬇  Baixar modelo selecionado (~4 GB)", self._pull_model, width=34).pack(anchor="w", pady=4)
        body(f, "Dica: llama3 é o mais capaz; phi3 é menor e mais rápido (~2 GB).",
             FG2).pack(anchor="w", pady=(4, 0))
        return f

    def _pull_model(self):
        if not ollama_installed():
            messagebox.showerror("Ollama não encontrado",
                                 "Instale o Ollama primeiro e reinicie.")
            return
        model = self._model_var.get()
        self._model_status.config(text=f"Baixando {model}… pode levar vários minutos.", fg=YELLOW)
        self._model_progress.start(12)

        def run():
            result = subprocess.run(["ollama", "pull", model], capture_output=True, text=True)
            self._model_progress.stop()
            if result.returncode == 0:
                self._model_status.config(text=f"✓ {model} pronto.", fg=GREEN)
            else:
                self._model_status.config(text=f"Erro ao baixar {model}.", fg=RED)

        threading.Thread(target=run, daemon=True).start()

    # ── Página 4 — Configuração ───────────────────────────────────────

    def _page_config(self) -> tk.Frame:
        f = styled_frame(self._content)
        h1(f, "Configuração").pack(anchor="w", pady=(0, 4))
        body(f, "Ajuste as opções básicas. Tudo pode ser alterado depois em "
                "core/config.yaml.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        def field(label, var, placeholder="", show=""):
            row = tk.Frame(f, bg=BG)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=BG, fg=FG2,
                     font=("Segoe UI", 8), width=22, anchor="w").pack(side="left")
            e = tk.Entry(row, textvariable=var, bg=BG2, fg=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 9), show=show,
                         highlightthickness=1, highlightcolor=ACCENT,
                         highlightbackground=BORDER)
            e.pack(side="left", fill="x", expand=True)
            if placeholder and not var.get():
                e.insert(0, placeholder)
                e.config(fg=FG2)
                def on_in(ev, entry=e, v=var):
                    if entry.get() == placeholder:
                        entry.delete(0, "end"); entry.config(fg=FG)
                def on_out(ev, entry=e, ph=placeholder):
                    if not entry.get():
                        entry.insert(0, ph); entry.config(fg=FG2)
                e.bind("<FocusIn>", on_in)
                e.bind("<FocusOut>", on_out)
            return e

        cfg = read_config()
        self._cfg_model    = tk.StringVar(value=cfg.get("ai", {}).get("model", "llama3"))
        self._cfg_password = tk.StringVar(value=cfg.get("web", {}).get("password", ""))
        self._cfg_obsidian = tk.StringVar(value=cfg.get("obsidian", {}).get("vault_path", ""))
        self._cfg_wakekey  = tk.StringVar(value=cfg.get("wake_word", {}).get("access_key", ""))

        field("Modelo LLM:", self._cfg_model, "llama3")
        field("Senha do dashboard:", self._cfg_password, "(vazio = sem senha)", show="*")

        obs_row = tk.Frame(f, bg=BG)
        obs_row.pack(fill="x", pady=4)
        tk.Label(obs_row, text="Vault Obsidian:", bg=BG, fg=FG2,
                 font=("Segoe UI", 8), width=22, anchor="w").pack(side="left")
        tk.Entry(obs_row, textvariable=self._cfg_obsidian, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 9),
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=BORDER).pack(side="left", fill="x", expand=True)
        btn(obs_row, "…", lambda: self._cfg_obsidian.set(
            filedialog.askdirectory(title="Selecione o vault do Obsidian") or self._cfg_obsidian.get()
        ), color=BG3, width=3).pack(side="left", padx=4)

        field("Picovoice access key:", self._cfg_wakekey,
              "(opcional — wake word 'Axiom')")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)
        self._cfg_status = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8))
        self._cfg_status.pack(anchor="w")
        btn(f, "Salvar configuração", self._save_config, width=20).pack(anchor="w", pady=4)
        return f

    def _save_config(self):
        values = {
            "ai":       {"model": self._cfg_model.get() or "llama3"},
            "web":      {"password": self._cfg_password.get()},
            "obsidian": {"vault_path": self._cfg_obsidian.get()},
            "wake_word":{"access_key": self._cfg_wakekey.get()},
        }
        result = write_config_values(values)
        if result is True:
            self._cfg_status.config(text="✓ Configuração salva.", fg=GREEN)
        else:
            self._cfg_status.config(text=f"Erro: {result}", fg=RED)

    # ── Página 5 — Google Auth ────────────────────────────────────────

    def _page_google(self) -> tk.Frame:
        f = styled_frame(self._content)
        h1(f, "Integração Google (opcional)").pack(anchor="w", pady=(0, 4))
        body(f, "Necessário para: ver agenda, criar eventos e backup no Google Drive. "
                "Pode pular — configure depois com 'axiom, autoriza calendário'.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        h2(f, "1. Criar credenciais OAuth").pack(anchor="w", pady=(0, 4))
        body(f,
             "• console.cloud.google.com → APIs & Services → Credenciais\n"
             "• Novo projeto → Ativar Calendar API e Drive API\n"
             "• Criar credenciais → OAuth 2.0 → Aplicativo desktop → Baixar JSON").pack(
             anchor="w", padx=8)
        btn(f, "Abrir Google Cloud Console",
            lambda: webbrowser.open("https://console.cloud.google.com/apis/credentials"),
            color=BG3, width=28).pack(anchor="w", pady=(6, 0))

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)
        h2(f, "2. Selecionar credentials.json").pack(anchor="w", pady=(0, 4))

        default_creds = INSTALL_DIR / "core" / "credentials.json"
        self._creds_var = tk.StringVar(
            value=str(default_creds) if default_creds.exists() else ""
        )
        creds_row = tk.Frame(f, bg=BG)
        creds_row.pack(fill="x", pady=2)
        tk.Label(creds_row, text="credentials.json:", bg=BG, fg=FG2,
                 font=("Segoe UI", 8), width=18, anchor="w").pack(side="left")
        tk.Entry(creds_row, textvariable=self._creds_var, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat", font=("Segoe UI", 8),
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=BORDER).pack(side="left", fill="x", expand=True)
        btn(creds_row, "…", self._pick_credentials, color=BG3, width=3).pack(side="left", padx=4)

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)
        h2(f, "3. Autorizar conta Google").pack(anchor="w", pady=(0, 6))

        token_ok = (INSTALL_DIR / "core" / "google_token.json").exists()
        grid = tk.Frame(f, bg=BG)
        grid.pack(fill="x")

        self._google_cal_dot = status_dot(grid, token_ok)
        self._google_cal_dot.grid(row=0, column=0, sticky="w")
        self._google_cal_lbl = tk.Label(grid, text="  Google Calendar",
                                         bg=BG, fg=FG, font=("Segoe UI", 9))
        self._google_cal_lbl.grid(row=0, column=1, sticky="w")

        self._google_drv_dot = status_dot(grid, token_ok)
        self._google_drv_dot.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self._google_drv_lbl = tk.Label(grid, text="  Google Drive",
                                         bg=BG, fg=FG, font=("Segoe UI", 9))
        self._google_drv_lbl.grid(row=1, column=1, sticky="w", pady=(2, 0))

        self._google_status = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8))
        self._google_status.pack(anchor="w", pady=(8, 2))
        btn(f, "Conectar conta Google", self._run_google_auth, width=22).pack(anchor="w")
        body(f, "Uma janela do navegador abrirá para você fazer login e autorizar o Axiom.",
             FG2).pack(anchor="w", pady=(6, 0))
        return f

    def _pick_credentials(self):
        path = filedialog.askopenfilename(
            title="Selecione credentials.json",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if path:
            self._creds_var.set(path)

    def _run_google_auth(self):
        creds_src = self._creds_var.get().strip()
        if not creds_src or not os.path.exists(creds_src):
            self._google_status.config(
                text="Selecione um arquivo credentials.json válido primeiro.", fg=RED)
            return
        if not pkg_installed("google_auth_oauthlib"):
            self._google_status.config(
                text="google-auth-oauthlib não instalado — instale as dependências (passo 2) primeiro.",
                fg=RED)
            return
        self._google_status.config(text="Abrindo navegador para autorização…", fg=YELLOW)

        def run():
            SCOPES = [
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/drive.file",
            ]
            dest_creds = INSTALL_DIR / "core" / "credentials.json"
            token_path = INSTALL_DIR / "core" / "google_token.json"
            exe = _find_python()

            try:
                if not exe:
                    raise RuntimeError("Python não encontrado.")

                if Path(creds_src).resolve() != dest_creds.resolve():
                    shutil.copy2(creds_src, dest_creds)

                # Roda o fluxo OAuth via subprocesso para evitar conflito com tkinter mainloop
                script = (
                    "from google_auth_oauthlib.flow import InstalledAppFlow\n"
                    "import json, sys\n"
                    "flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], json.loads(sys.argv[2]))\n"
                    "creds = flow.run_local_server(port=0)\n"
                    "open(sys.argv[3],'w').write(creds.to_json())\n"
                    "print('OK')\n"
                )
                r = subprocess.run(
                    [exe, "-c", script,
                     str(dest_creds), json.dumps(SCOPES), str(token_path)],
                    capture_output=True, text=True, timeout=120,
                )
                if r.returncode != 0 or "OK" not in r.stdout:
                    raise RuntimeError(r.stderr.strip() or "Autorização cancelada.")

                def _ok():
                    self._google_cal_dot.config(fg=GREEN)
                    self._google_drv_dot.config(fg=GREEN)
                    self._google_cal_lbl.config(text="  Google Calendar  ✓")
                    self._google_drv_lbl.config(text="  Google Drive  ✓")
                    self._google_status.config(text="Conta Google conectada com sucesso.", fg=GREEN)

                self.after(0, _ok)
            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._google_status.config(text=f"Erro: {err}", fg=RED))

        threading.Thread(target=run, daemon=True).start()

    # ── Página 6 — Concluído ──────────────────────────────────────────

    def _page_finish(self) -> tk.Frame:
        f = styled_frame(self._content)
        f._on_show = lambda: self._finish_init(f)
        return f

    def _finish_init(self, f):
        for w in f.winfo_children():
            w.destroy()

        h1(f, "Tudo pronto!").pack(anchor="w", pady=(0, 4))
        body(f, "O Axiom está configurado e pronto para usar.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=12)

        py_exe = _find_python()
        checks = [
            ("Python 3.9+",       bool(py_exe)),
            ("pyyaml instalado",  pkg_installed("yaml")),
            ("psutil instalado",  pkg_installed("psutil")),
            ("faster-whisper",    pkg_installed("faster_whisper")),
            ("FastAPI/uvicorn",   pkg_installed("fastapi")),
            ("Ollama disponível", ollama_installed()),
            ("Google autorizado", (INSTALL_DIR / "core" / "google_token.json").exists()),
        ]
        for label, ok in checks:
            row = tk.Frame(f, bg=BG)
            row.pack(fill="x", pady=2)
            status_dot(row, ok).pack(side="left")
            tk.Label(row, text=f"  {label}", bg=BG, fg=FG if ok else FG2,
                     font=("Segoe UI", 9)).pack(side="left")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=12)

        self._shortcut_status = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8))
        self._shortcut_status.pack(anchor="w", pady=(0, 4))

        def make_shortcut():
            try:
                create_shortcut()
                self._shortcut_status.config(text="✓ Atalho criado na área de trabalho.", fg=GREEN)
            except Exception as e:
                self._shortcut_status.config(text=f"Erro: {e}", fg=RED)

        def launch(extra_args=()):
            exe = _find_python()
            if not exe:
                messagebox.showerror("Python não encontrado",
                                     "Instale o Python (passo 1) e reinicie o wizard.")
                return
            flags = subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0
            subprocess.Popen(
                [exe, "main.py", "--mode", "text", "--no-tts"] + list(extra_args),
                cwd=str(INSTALL_DIR), creationflags=flags,
            )
            self.destroy()

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w", pady=4)
        btn(btn_row, "🖥  Criar atalho", make_shortcut, color=BG3, width=14).pack(side="left")
        btn(btn_row, "▶  Iniciar Axiom", lambda: launch(), width=14).pack(side="left", padx=8)
        btn(btn_row, "🌐  Com dashboard", lambda: launch(["--web"]),
            color="#1f5f2e", width=16).pack(side="left")

        body(f, "\npython main.py --mode text --no-tts\n"
                "python main.py --web   (com dashboard)\n"
                "python main.py         (modo completo com voz)",
             FG2).pack(anchor="w")


# ── Entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    os.chdir(INSTALL_DIR)
    app = WizardApp()
    app.mainloop()
