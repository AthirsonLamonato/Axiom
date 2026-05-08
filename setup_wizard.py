"""
setup_wizard.py — Assistente de instalação visual do Axiom
Usa apenas tkinter (stdlib) — funciona sem instalar nada primeiro.
Gera: atalho na área de trabalho + core/config.yaml configurado.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk

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

INSTALL_DIR = Path(__file__).parent.resolve()
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


# ── Utilitários ───────────────────────────────────────────────────────

def pip_install(pkg: str, callback=None):
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
        capture_output=True, text=True,
    )
    if callback:
        callback(pkg, result.returncode == 0)
    return result.returncode == 0


def pkg_installed(name: str) -> bool:
    clean = name.split("[")[0].replace("-", "_")
    try:
        __import__(clean)
        return True
    except ImportError:
        return False


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
        import yaml
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def write_config_values(values: dict):
    cfg_path = INSTALL_DIR / "core" / "config.yaml"
    try:
        import yaml
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # Aplica recursivamente só as chaves enviadas
        for section, subdict in values.items():
            if section not in data or not isinstance(data[section], dict):
                data[section] = {}
            data[section].update(subdict)
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return True
    except Exception as e:
        return str(e)


def create_shortcut():
    if platform.system() != "Windows":
        return
    desktop = Path.home() / "Desktop"
    bat = desktop / "Axiom.bat"
    bat.write_text(
        f'@echo off\ncd /d "{INSTALL_DIR}"\n'
        f'"{sys.executable}" main.py\npause\n',
        encoding="utf-8",
    )
    # Tenta criar .lnk se win32com disponível
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        lnk = shell.CreateShortCut(str(desktop / "Axiom.lnk"))
        lnk.TargetPath = sys.executable
        lnk.Arguments = "main.py"
        lnk.WorkingDirectory = str(INSTALL_DIR)
        lnk.Description = "Axiom — Assistente pessoal inteligente"
        lnk.save()
        bat.unlink(missing_ok=True)   # prefere .lnk
    except Exception:
        pass  # .bat já criado como fallback


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


def sep(parent) -> ttk.Separator:
    s = ttk.Separator(parent, orient="horizontal")
    return s


def btn(parent, text, command, color=ACCENT, width=14) -> tk.Button:
    return tk.Button(
        parent, text=text, command=command,
        bg=color, fg="white", activebackground=color,
        relief="flat", padx=10, pady=6,
        font=("Segoe UI", 9), width=width, cursor="hand2",
    )


def status_dot(parent, ok: bool) -> tk.Label:
    return tk.Label(parent, text="●", bg=BG,
                    fg=GREEN if ok else RED,
                    font=("Segoe UI", 10))


# ── Janela principal ──────────────────────────────────────────────────

class WizardApp(tk.Tk):
    PAGES = ["Boas-vindas", "Dependências", "Ollama & IA", "Configuração", "Concluído"]

    def __init__(self):
        super().__init__()
        self.title("Axiom — Assistente de instalação")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("540x560")
        self._center()

        self._page_idx = 0
        self._frames: list[tk.Frame] = []
        self._build_chrome()
        self._build_pages()
        self._show_page(0)

    def _center(self):
        self.update_idletasks()
        w, h = 540, 560
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Cromo (header + nav) ──────────────────────────────────────────

    def _build_chrome(self):
        # Header
        hdr = tk.Frame(self, bg=BG2, height=70)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚡ AXIOM", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 20, "bold")).pack(side="left", padx=20, pady=12)
        self._step_lbl = tk.Label(hdr, text="", bg=BG2, fg=FG2,
                                   font=("Segoe UI", 9))
        self._step_lbl.pack(side="right", padx=20)

        # Barra de progresso
        self._progress = ttk.Progressbar(self, length=540, mode="determinate",
                                          maximum=len(self.PAGES) - 1)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=BG3,
                        background=ACCENT, thickness=4)
        self._progress.pack(fill="x")

        # Área de conteúdo
        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True, padx=24, pady=16)

        # Nav inferior
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
        # Inicialização sob demanda
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
            self._page_finish(),
        ]
        for f in self._frames:
            f.pack(fill="both", expand=True)
            f.pack_forget()

    # Página 1 — Boas-vindas
    def _page_welcome(self) -> tk.Frame:
        f = styled_frame(self._content)

        h1(f, "Bem-vindo ao Axiom").pack(anchor="w", pady=(0, 4))
        body(f, "Assistente pessoal de desktop — controle por voz ou texto, "
                "100% local e gratuito.").pack(anchor="w")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        h2(f, "Verificação do sistema").pack(anchor="w", pady=(0, 8))

        info = tk.Frame(f, bg=BG2, padx=12, pady=10)
        info.pack(fill="x")

        py_ok = sys.version_info >= (3, 9)
        rows = [
            (f"Python {sys.version.split()[0]}", py_ok),
            (f"Sistema: {platform.system()} {platform.release()}", True),
            (f"Diretório: {INSTALL_DIR}", True),
        ]
        for label, ok in rows:
            row = tk.Frame(info, bg=BG2)
            row.pack(fill="x", pady=2)
            status_dot(row, ok).pack(side="left")
            tk.Label(row, text=f"  {label}", bg=BG2, fg=FG,
                     font=("Segoe UI", 9)).pack(side="left")

        if not py_ok:
            body(f, "⚠  Python 3.9+ é necessário. Instale em python.org",
                 RED).pack(anchor="w", pady=(10, 0))

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        body(f, "Este assistente irá:\n"
                "  1. Instalar as dependências Python\n"
                "  2. Configurar o Ollama (IA local)\n"
                "  3. Ajustar suas preferências\n"
                "  4. Criar um atalho na área de trabalho").pack(anchor="w")
        return f

    # Página 2 — Dependências
    def _page_deps(self) -> tk.Frame:
        f = styled_frame(self._content)
        h1(f, "Dependências Python").pack(anchor="w", pady=(0, 4))
        body(f, "Pacotes necessários para o Axiom funcionar.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        # Lista com status
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
            lbl = tk.Label(row, text=lbl_text, bg=BG2, fg=FG if installed else FG2,
                           font=("Segoe UI", 8))
            lbl.pack(side="left")
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
        btn(btn_row, "Só opcionais", lambda: self._install_deps(optional_only=True),
            color=BG3, width=13).pack(side="left", padx=8)
        return f

    def _install_deps(self, optional_only=False):
        pkgs = (
            [p for p, _ in PACKAGES_OPTIONAL]
            if optional_only
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

    # Página 3 — Ollama
    def _page_ollama(self) -> tk.Frame:
        f = styled_frame(self._content)
        h1(f, "Ollama & Modelo de IA").pack(anchor="w", pady=(0, 4))
        body(f, "O Axiom usa o Ollama para rodar um LLM local. "
                "Sem internet após o download.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        # Status Ollama
        status_frame = tk.Frame(f, bg=BG2, padx=12, pady=10)
        status_frame.pack(fill="x")
        self._ollama_dot = status_dot(status_frame, ollama_installed())
        self._ollama_dot.pack(side="left")
        self._ollama_lbl = tk.Label(
            status_frame,
            text=f"  Ollama {'encontrado' if ollama_installed() else 'não encontrado'}",
            bg=BG2, fg=FG, font=("Segoe UI", 9)
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
                                 "Instale o Ollama primeiro e reinicie o terminal.")
            return
        model = self._model_var.get()
        self._model_status.config(text=f"Baixando {model}… pode levar vários minutos.", fg=YELLOW)
        self._model_progress.start(12)

        def run():
            result = subprocess.run(["ollama", "pull", model],
                                    capture_output=True, text=True)
            self._model_progress.stop()
            if result.returncode == 0:
                self._model_status.config(text=f"✓ {model} pronto.", fg=GREEN)
            else:
                self._model_status.config(text=f"Erro ao baixar {model}.", fg=RED)

        threading.Thread(target=run, daemon=True).start()

    # Página 4 — Configuração
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
                def on_focus_in(ev, entry=e, v=var):
                    if entry.get() == placeholder:
                        entry.delete(0, "end")
                        entry.config(fg=FG)
                def on_focus_out(ev, entry=e, ph=placeholder, v=var):
                    if not entry.get():
                        entry.insert(0, ph)
                        entry.config(fg=FG2)
                e.bind("<FocusIn>", on_focus_in)
                e.bind("<FocusOut>", on_focus_out)
            return e

        cfg = read_config()

        self._cfg_model    = tk.StringVar(value=cfg.get("ai", {}).get("model", "llama3"))
        self._cfg_password = tk.StringVar(value=cfg.get("web", {}).get("password", ""))
        self._cfg_obsidian = tk.StringVar(value=cfg.get("obsidian", {}).get("vault_path", ""))
        self._cfg_wakekey  = tk.StringVar(value=cfg.get("wake_word", {}).get("access_key", ""))

        field("Modelo LLM:", self._cfg_model, "llama3")
        field("Senha do dashboard:", self._cfg_password, "(vazio = sem senha)", show="*")

        # Obsidian com botão de pasta
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
            "ai": {"model": self._cfg_model.get() or "llama3"},
            "web": {"password": self._cfg_password.get()},
            "obsidian": {"vault_path": self._cfg_obsidian.get()},
            "wake_word": {"access_key": self._cfg_wakekey.get()},
        }
        result = write_config_values(values)
        if result is True:
            self._cfg_status.config(text="✓ Configuração salva.", fg=GREEN)
        else:
            self._cfg_status.config(text=f"Erro: {result}", fg=RED)

    # Página 5 — Concluído
    def _page_finish(self) -> tk.Frame:
        f = styled_frame(self._content)
        f._on_show = lambda: self._finish_init(f)
        return f

    def _finish_init(self, f):
        for w in f.winfo_children():
            w.destroy()
        h1(f, "Tudo pronto! 🎉").pack(anchor="w", pady=(0, 4))
        body(f, "O Axiom está configurado e pronto para usar.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=12)

        checks = [
            ("Python 3.9+",        sys.version_info >= (3, 9)),
            ("pyyaml instalado",   pkg_installed("yaml")),
            ("psutil instalado",   pkg_installed("psutil")),
            ("faster-whisper",     pkg_installed("faster_whisper")),
            ("FastAPI/uvicorn",    pkg_installed("fastapi")),
            ("Ollama disponível",  ollama_installed()),
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
                self._shortcut_status.config(text=f"Erro ao criar atalho: {e}", fg=RED)

        def launch():
            subprocess.Popen(
                [sys.executable, "main.py", "--mode", "text", "--no-tts"],
                cwd=str(INSTALL_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0,
            )
            self.destroy()

        def launch_web():
            subprocess.Popen(
                [sys.executable, "main.py", "--mode", "text", "--no-tts", "--web"],
                cwd=str(INSTALL_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0,
            )
            self.destroy()

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w", pady=4)
        btn(btn_row, "🖥  Criar atalho", make_shortcut, color=BG3, width=14).pack(side="left")
        btn(btn_row, "▶  Iniciar Axiom", launch, width=14).pack(side="left", padx=8)
        btn(btn_row, "🌐  Com dashboard", launch_web, color="#1f5f2e", width=16).pack(side="left")

        body(f, "\nPara iniciar manualmente:\n"
                "  python main.py --mode text --no-tts\n"
                "  python main.py --web          (com dashboard)\n"
                "  python main.py                (modo completo com voz)",
             FG2).pack(anchor="w")


# ── Entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    os.chdir(INSTALL_DIR)
    app = WizardApp()
    app.mainloop()
