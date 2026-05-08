"""
setup_wizard.py — Assistente de instalação visual do Paçoca
Funciona em qualquer PC Windows — sem Python, sem pip install.
Paçoca.exe já traz todas as dependências bundled.
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
        if exe_dir.name == "dist" and (exe_dir.parent / "main.py").exists():
            return exe_dir.parent   # dev: rodando de dist/
        return exe_dir
    return Path(__file__).parent.resolve()


INSTALL_DIR = _detect_install_dir()
PACOCA_EXE   = INSTALL_DIR / "Pacoca" / "Pacoca.exe"   # onedir build


# ── Ollama ────────────────────────────────────────────────────────────

def ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def ollama_model_exists(model: str = "llama3") -> bool:
    if not ollama_installed():
        return False
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    return model in r.stdout


# ── Config ────────────────────────────────────────────────────────────

def _cfg_path() -> Path:
    return INSTALL_DIR / "core" / "config.yaml"


def read_config() -> dict:
    try:
        import yaml
        with open(_cfg_path(), encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def write_config_values(values: dict):
    path = _cfg_path()
    try:
        import yaml
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        for section, subdict in values.items():
            if isinstance(data.get(section), dict):
                data[section].update(subdict)
            else:
                data[section] = subdict
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return True
    except Exception as e:
        return str(e)


# ── Shortcut ──────────────────────────────────────────────────────────

def create_shortcut():
    if platform.system() != "Windows":
        return
    desktop = Path.home() / "Desktop"
    target  = str(PACOCA_EXE) if PACOCA_EXE.exists() else ""
    if not target:
        return

    bat = desktop / "Pacoca.bat"
    bat.write_text(
        f'@echo off\nstart "" "{target}"\n',
        encoding="utf-8",
    )
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        lnk = shell.CreateShortCut(str(desktop / "Pacoca.lnk"))
        lnk.TargetPath = target
        lnk.WorkingDirectory = str(PACOCA_EXE.parent)
        lnk.Description = "Paçoca — Assistente pessoal inteligente"
        lnk.save()
        bat.unlink(missing_ok=True)
    except Exception:
        pass   # .bat já criado como fallback


# ── Widgets reutilizáveis ─────────────────────────────────────────────

def styled_frame(parent, **kw):
    return tk.Frame(parent, bg=BG, **kw)

def h1(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=ACCENT,
                    font=("Segoe UI", 18, "bold"))

def h2(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=FG,
                    font=("Segoe UI", 11, "bold"))

def body(parent, text, color=FG2):
    return tk.Label(parent, text=text, bg=BG, fg=color,
                    font=("Segoe UI", 9), wraplength=480, justify="left")

def btn(parent, text, command, color=ACCENT, width=14):
    return tk.Button(
        parent, text=text, command=command,
        bg=color, fg="white", activebackground=color,
        relief="flat", padx=10, pady=6,
        font=("Segoe UI", 9), width=width, cursor="hand2",
    )

def status_dot(parent, ok=None):
    color = GREEN if ok is True else (RED if ok is False else YELLOW)
    return tk.Label(parent, text="●", bg=BG, fg=color, font=("Segoe UI", 10))


# ── Wizard ────────────────────────────────────────────────────────────

class WizardApp(tk.Tk):
    PAGES = ["Boas-vindas", "Ollama & IA", "Configuração", "Google", "Concluído"]

    def __init__(self):
        super().__init__()
        self.title("Paçoca — Assistente de instalação")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("540x560")
        self._center()
        self._page_idx = 0
        self._frames: list = []
        self._build_chrome()
        self._build_pages()
        self._show_page(0)

    def _center(self):
        self.update_idletasks()
        w, h = 540, 560
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Cromo ─────────────────────────────────────────────────────────

    def _build_chrome(self):
        hdr = tk.Frame(self, bg=BG2, height=70)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚡ PAÇOCA", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 20, "bold")).pack(side="left", padx=20, pady=12)
        self._step_lbl = tk.Label(hdr, text="", bg=BG2, fg=FG2, font=("Segoe UI", 9))
        self._step_lbl.pack(side="right", padx=20)

        self._progress = ttk.Progressbar(self, length=540, mode="determinate",
                                          maximum=len(self.PAGES) - 1)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=BG3, background=ACCENT, thickness=4)
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
            text=f"Etapa {idx + 1}/{len(self.PAGES)}  —  {self.PAGES[idx]}"
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

    def _build_pages(self):
        self._frames = [
            self._page_welcome(),
            self._page_ollama(),
            self._page_config(),
            self._page_google(),
            self._page_finish(),
        ]
        for f in self._frames:
            f.pack(fill="both", expand=True)
            f.pack_forget()

    # ── URL do app no GitHub Releases ─────────────────────────────────
    _APP_ZIP_URL = (
        "https://github.com/AthirsonLamonato/Pacoca/releases/download"
        "/v0.5.0/Pacoca-app-v0.5.0.zip"
    )

    # ── Credenciais OAuth do desenvolvedor (embutidas no app) ──────────
    # Crie em: console.cloud.google.com → APIs & Services → Credenciais
    #   → Criar credenciais → OAuth 2.0 → Aplicativo desktop
    # Copie client_id e client_secret aqui. O usuário final não precisa
    # fazer nada no Google Cloud — só clicar em "Login com Google".
    _GOOGLE_CLIENT_ID     = ""   # preencha: "...apps.googleusercontent.com"
    _GOOGLE_CLIENT_SECRET = ""   # preencha: "GOCSPX-..."

    # ── Página 1 — Boas-vindas ────────────────────────────────────────

    def _page_welcome(self):
        f = styled_frame(self._content)
        h1(f, "Bem-vindo ao Paçoca").pack(anchor="w", pady=(0, 4))
        body(f, "Assistente pessoal de desktop — controle por voz ou texto, "
                "100% local e gratuito. Sem pip install — tudo já está no executável.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        h2(f, "Verificação do sistema").pack(anchor="w", pady=(0, 8))

        info = tk.Frame(f, bg=BG2, padx=12, pady=10)
        info.pack(fill="x")

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

        # Linha do Pacoca.exe — mantemos referência para atualizar após download
        pacoca_row = tk.Frame(info, bg=BG2)
        pacoca_row.pack(fill="x", pady=2)
        self._welcome_pacoca_dot = status_dot(pacoca_row, PACOCA_EXE.exists())
        self._welcome_pacoca_dot.pack(side="left")
        self._welcome_pacoca_lbl = tk.Label(
            pacoca_row,
            text=f"  Pacoca.exe: {PACOCA_EXE}" if PACOCA_EXE.exists() else "  Pacoca.exe: não encontrado",
            bg=BG2, fg=FG, font=("Segoe UI", 9),
        )
        self._welcome_pacoca_lbl.pack(side="left")

        # Seção de download — visível apenas quando o app não está presente
        self._dl_section = tk.Frame(f, bg=BG3, padx=12, pady=10)
        if not PACOCA_EXE.exists():
            self._dl_section.pack(fill="x", pady=(8, 0))

        body(self._dl_section,
             "Pacoca.exe não encontrado. Clique abaixo para baixar o app (~175 MB).",
             YELLOW).pack(anchor="w")

        self._dl_progress = ttk.Progressbar(
            self._dl_section, length=460, mode="determinate", maximum=100
        )
        self._dl_progress.pack(fill="x", pady=(6, 2))

        self._dl_status = tk.Label(
            self._dl_section, text="", bg=BG3, fg=FG2, font=("Segoe UI", 8)
        )
        self._dl_status.pack(anchor="w", pady=(0, 4))

        btn(self._dl_section, "⬇  Baixar Paçoca (~175 MB)",
            self._download_app, width=26).pack(anchor="w")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        body(f, "Este assistente irá:\n"
                "  1. Configurar o Ollama (IA local)\n"
                "  2. Ajustar suas preferências\n"
                "  3. Fazer login com o Google (Calendar + Drive)\n"
                "  4. Criar um atalho na área de trabalho").pack(anchor="w")
        return f

    def _download_app(self):
        """Baixa Pacoca-app-v0.5.0.zip do GitHub Releases e extrai em INSTALL_DIR."""
        import tempfile, zipfile as zf

        self._dl_status.config(text="Iniciando download…", fg=YELLOW)
        self._dl_progress.config(value=0)

        def run():
            try:
                tmp = Path(tempfile.mktemp(suffix=".zip"))

                def reporthook(count, block_size, total_size):
                    if total_size > 0:
                        pct = int(count * block_size * 100 / total_size)
                        self.after(0, lambda p=pct: self._dl_progress.config(value=min(p, 100)))
                        self.after(0, lambda p=pct: self._dl_status.config(
                            text=f"Baixando… {min(p, 100)}%", fg=YELLOW))

                urllib.request.urlretrieve(self._APP_ZIP_URL, str(tmp), reporthook)

                self.after(0, lambda: self._dl_status.config(text="Extraindo…", fg=YELLOW))
                with zf.ZipFile(str(tmp), "r") as z:
                    z.extractall(str(INSTALL_DIR))
                tmp.unlink(missing_ok=True)

                self.after(0, self._on_app_downloaded)

            except Exception as e:
                self.after(0, lambda: self._dl_status.config(
                    text=f"Erro: {e}", fg=RED))

        threading.Thread(target=run, daemon=True).start()

    def _on_app_downloaded(self):
        """Chamado após download concluído — atualiza UI da página 1."""
        ok = PACOCA_EXE.exists()
        self._dl_progress.config(value=100)
        if ok:
            self._dl_status.config(text="✓ Pacoca.exe pronto!", fg=GREEN)
            self._welcome_pacoca_dot.config(fg=GREEN)
            self._welcome_pacoca_lbl.config(text=f"  Pacoca.exe: {PACOCA_EXE}")
            self._dl_section.pack_forget()
        else:
            self._dl_status.config(
                text="Download concluído mas Pacoca.exe ainda não encontrado. "
                     "Verifique se o ZIP contém a pasta Pacoca/.",
                fg=YELLOW)

    # ── Página 2 — Ollama ─────────────────────────────────────────────

    def _page_ollama(self):
        f = styled_frame(self._content)
        h1(f, "Ollama & Modelo de IA").pack(anchor="w", pady=(0, 4))
        body(f, "O Paçoca usa o Ollama para rodar um LLM local. "
                "Sem internet após o download.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        sf = tk.Frame(f, bg=BG2, padx=12, pady=10)
        sf.pack(fill="x")
        self._ollama_dot = status_dot(sf, ollama_installed())
        self._ollama_dot.pack(side="left")
        self._ollama_lbl = tk.Label(sf,
            text=f"  Ollama {'encontrado' if ollama_installed() else 'não encontrado'}",
            bg=BG2, fg=FG, font=("Segoe UI", 9))
        self._ollama_lbl.pack(side="left")

        def refresh():
            ok = ollama_installed()
            self._ollama_dot.config(fg=GREEN if ok else RED)
            self._ollama_lbl.config(text=f"  Ollama {'encontrado' if ok else 'não encontrado'}")

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w", pady=8)
        btn(btn_row, "Baixar Ollama",
            lambda: [webbrowser.open("https://ollama.com/download"), refresh()],
            width=14).pack(side="left")
        btn(btn_row, "↺ Verificar", refresh, color=BG3, width=10).pack(side="left", padx=8)

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=8)
        h2(f, "Modelo de linguagem").pack(anchor="w", pady=(0, 6))

        mf = tk.Frame(f, bg=BG)
        mf.pack(anchor="w")
        tk.Label(mf, text="Modelo:", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        self._model_var = tk.StringVar(value="llama3")
        for m in ("llama3", "mistral", "phi3"):
            tk.Radiobutton(mf, text=m, variable=self._model_var, value=m,
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
            messagebox.showerror("Ollama não encontrado", "Instale o Ollama primeiro.")
            return
        model = self._model_var.get()
        self._model_status.config(text=f"Baixando {model}… pode levar vários minutos.", fg=YELLOW)
        self._model_progress.start(12)

        def run():
            r = subprocess.run(["ollama", "pull", model], capture_output=True, text=True)
            self._model_progress.stop()
            ok = r.returncode == 0
            self._model_status.config(
                text=f"✓ {model} pronto." if ok else f"Erro ao baixar {model}.",
                fg=GREEN if ok else RED)

        threading.Thread(target=run, daemon=True).start()

    # ── Página 3 — Configuração ───────────────────────────────────────

    def _page_config(self):
        f = styled_frame(self._content)
        h1(f, "Configuração").pack(anchor="w", pady=(0, 4))
        body(f, "Ajuste as opções básicas. Salvas em core/config.yaml.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        def field(label, var, placeholder="", show=""):
            row = tk.Frame(f, bg=BG)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=BG, fg=FG2,
                     font=("Segoe UI", 8), width=22, anchor="w").pack(side="left")
            e = tk.Entry(row, textvariable=var, bg=BG2, fg=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI", 9), show=show,
                         highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER)
            e.pack(side="left", fill="x", expand=True)
            if placeholder and not var.get():
                e.insert(0, placeholder); e.config(fg=FG2)
                def on_in(ev, en=e, ph=placeholder):
                    if en.get() == ph: en.delete(0, "end"); en.config(fg=FG)
                def on_out(ev, en=e, ph=placeholder):
                    if not en.get(): en.insert(0, ph); en.config(fg=FG2)
                e.bind("<FocusIn>", on_in); e.bind("<FocusOut>", on_out)
            return e

        cfg = read_config()
        self._cfg_model     = tk.StringVar(value=cfg.get("ai", {}).get("model", "llama3"))
        self._cfg_password  = tk.StringVar(value=cfg.get("web", {}).get("password", ""))
        self._cfg_obsidian  = tk.StringVar(value=cfg.get("obsidian", {}).get("vault_path", ""))
        self._cfg_wakemodel = tk.StringVar(value=cfg.get("wake_word", {}).get("model_path", ""))

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

        field("Modelo wake word (.onnx):", self._cfg_wakemodel,
              "(opcional — ex: pacoca.onnx; vazio = hey_jarvis padrão)")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)
        self._cfg_status = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8))
        self._cfg_status.pack(anchor="w")
        btn(f, "Salvar configuração", self._save_config, width=20).pack(anchor="w", pady=4)
        return f

    def _save_config(self):
        values = {
            "ai":        {"model": self._cfg_model.get() or "llama3"},
            "web":       {"password": self._cfg_password.get()},
            "obsidian":  {"vault_path": self._cfg_obsidian.get()},
            "wake_word": {"model_path": self._cfg_wakemodel.get()},
        }
        result = write_config_values(values)
        if result is True:
            self._cfg_status.config(text="✓ Configuração salva.", fg=GREEN)
        else:
            self._cfg_status.config(text=f"Erro: {result}", fg=RED)

    # ── Página 4 — Google Auth ────────────────────────────────────────

    def _page_google(self):
        f = styled_frame(self._content)
        h1(f, "Integração Google").pack(anchor="w", pady=(0, 4))
        body(f, "Conecte sua conta Google para usar o Calendário e o Drive. "
                "Não é necessário criar nenhum projeto — basta fazer login.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=12)

        # Dots de status
        token_ok = (INSTALL_DIR / "core" / "google_token.json").exists()
        grid = tk.Frame(f, bg=BG)
        grid.pack(fill="x", pady=(0, 4))

        self._cal_dot = status_dot(grid, token_ok)
        self._cal_dot.grid(row=0, column=0, sticky="w")
        self._cal_lbl = tk.Label(grid, text="  Google Calendar",
                                  bg=BG, fg=FG, font=("Segoe UI", 9))
        self._cal_lbl.grid(row=0, column=1, sticky="w")

        self._drv_dot = status_dot(grid, token_ok)
        self._drv_dot.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self._drv_lbl = tk.Label(grid, text="  Google Drive",
                                  bg=BG, fg=FG, font=("Segoe UI", 9))
        self._drv_lbl.grid(row=1, column=1, sticky="w", pady=(2, 0))

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=12)

        self._google_status = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8),
                                        wraplength=480, justify="left")
        self._google_status.pack(anchor="w", pady=(0, 6))

        btn(f, "  Login com Google  ", self._run_google_auth, width=22).pack(anchor="w")
        body(f, "Uma janela do navegador abrirá. Escolha sua conta e clique em Permitir.",
             FG2).pack(anchor="w", pady=(6, 0))

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)

        skip_row = tk.Frame(f, bg=BG)
        skip_row.pack(anchor="w")
        body(skip_row, "Não precisa agora?", FG2).pack(side="left")
        tk.Button(
            skip_row, text="  Pular esta etapa →  ",
            command=self._go_next,
            bg=BG, fg=FG2, activebackground=BG2, activeforeground=FG,
            relief="flat", font=("Segoe UI", 9), cursor="hand2",
            borderwidth=0,
        ).pack(side="left", padx=6)
        body(skip_row, "(configure depois dizendo 'paçoca, autoriza calendário')",
             FG2).pack(side="left")
        return f

    def _run_google_auth(self):
        if not self._GOOGLE_CLIENT_ID or not self._GOOGLE_CLIENT_SECRET:
            self._google_status.config(
                text="Credenciais OAuth não configuradas no app. "
                     "O desenvolvedor precisa preencher _GOOGLE_CLIENT_ID e "
                     "_GOOGLE_CLIENT_SECRET em setup_wizard.py.",
                fg=YELLOW,
            )
            return

        self._google_status.config(text="Abrindo navegador para login…", fg=YELLOW)

        SCOPES = [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.file",
        ]
        token_path  = INSTALL_DIR / "core" / "google_token.json"
        creds_path  = INSTALL_DIR / "core" / "credentials.json"

        # Constrói o client_config a partir das constantes embutidas
        client_config = {
            "installed": {
                "client_id":      self._GOOGLE_CLIENT_ID,
                "client_secret":  self._GOOGLE_CLIENT_SECRET,
                "auth_uri":       "https://accounts.google.com/o/oauth2/auth",
                "token_uri":      "https://oauth2.googleapis.com/token",
                "redirect_uris":  ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            }
        }

        def run():
            try:
                token_path.parent.mkdir(parents=True, exist_ok=True)

                try:
                    from google_auth_oauthlib.flow import InstalledAppFlow
                    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                    creds = flow.run_local_server(port=0)
                    token_path.write_text(creds.to_json(), encoding="utf-8")
                    # Salva credentials.json para que os módulos possam fazer refresh
                    creds_path.write_text(json.dumps(client_config), encoding="utf-8")
                except ImportError:
                    exe = _find_system_python()
                    if not exe:
                        raise RuntimeError(
                            "google-auth-oauthlib não disponível. "
                            "Execute o Paçoca.exe uma vez e tente novamente.")
                    script = (
                        "from google_auth_oauthlib.flow import InstalledAppFlow\n"
                        "import json,sys\n"
                        "cfg=json.loads(sys.argv[1])\n"
                        "scopes=json.loads(sys.argv[2])\n"
                        "f=InstalledAppFlow.from_client_config(cfg,scopes)\n"
                        "c=f.run_local_server(port=0)\n"
                        "open(sys.argv[3],'w').write(c.to_json())\n"
                        "open(sys.argv[4],'w').write(sys.argv[1])\n"
                        "print('OK')\n"
                    )
                    r = subprocess.run(
                        [exe, "-c", script,
                         json.dumps(client_config), json.dumps(SCOPES),
                         str(token_path), str(creds_path)],
                        capture_output=True, text=True, timeout=120,
                    )
                    if r.returncode != 0 or "OK" not in r.stdout:
                        raise RuntimeError(r.stderr.strip() or "Autorização cancelada.")

                def _ok():
                    self._cal_dot.config(fg=GREEN)
                    self._drv_dot.config(fg=GREEN)
                    self._cal_lbl.config(text="  Google Calendar  ✓")
                    self._drv_lbl.config(text="  Google Drive  ✓")
                    self._google_status.config(text="✓ Conta Google conectada.", fg=GREEN)

                self.after(0, _ok)
            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._google_status.config(text=f"Erro: {err}", fg=RED))

        threading.Thread(target=run, daemon=True).start()

    # ── Página 5 — Concluído ──────────────────────────────────────────

    def _page_finish(self):
        f = styled_frame(self._content)
        f._on_show = lambda: self._finish_init(f)
        return f

    def _finish_init(self, f):
        for w in f.winfo_children():
            w.destroy()

        h1(f, "Tudo pronto!").pack(anchor="w", pady=(0, 4))
        body(f, "O Paçoca está configurado e pronto para usar.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=12)

        cfg_path = _cfg_path()
        checks = [
            ("Paçoca.exe encontrado",    PACOCA_EXE.exists()),
            ("Ollama disponível",        ollama_installed()),
            ("config.yaml configurado",  cfg_path.exists()),
            ("Google autorizado",        (INSTALL_DIR / "core" / "google_token.json").exists()),
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
            if not PACOCA_EXE.exists():
                self._shortcut_status.config(text="Paçoca.exe não encontrado.", fg=RED)
                return
            try:
                create_shortcut()
                self._shortcut_status.config(text="✓ Atalho criado na área de trabalho.", fg=GREEN)
            except Exception as e:
                self._shortcut_status.config(text=f"Erro: {e}", fg=RED)

        def launch():
            if not PACOCA_EXE.exists():
                messagebox.showerror("Paçoca.exe não encontrado",
                                     f"Esperado em:\n{PACOCA_EXE}")
                return
            flags = subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0
            subprocess.Popen(
                [str(PACOCA_EXE), "--mode", "text", "--no-tts"],
                cwd=str(PACOCA_EXE.parent),
                creationflags=flags,
            )
            self.destroy()

        def launch_web():
            if not PACOCA_EXE.exists():
                messagebox.showerror("Paçoca.exe não encontrado",
                                     f"Esperado em:\n{PACOCA_EXE}")
                return
            flags = subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0
            subprocess.Popen(
                [str(PACOCA_EXE), "--mode", "text", "--no-tts", "--web"],
                cwd=str(PACOCA_EXE.parent),
                creationflags=flags,
            )
            self.destroy()

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w", pady=4)
        btn(btn_row, "🖥  Criar atalho",    make_shortcut, color=BG3, width=14).pack(side="left")
        btn(btn_row, "▶  Iniciar Paçoca",   launch, width=14).pack(side="left", padx=8)
        btn(btn_row, "🌐  Com dashboard",  launch_web, color="#1f5f2e", width=16).pack(side="left")


# ── Helpers ───────────────────────────────────────────────────────────

def _find_system_python() -> str:
    """Fallback: procura Python real no sistema (para OAuth se não bundled)."""
    for name in ("python3", "python"):
        p = shutil.which(name)
        if p:
            try:
                r = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
                if re.search(r"Python 3\.\d+", r.stdout + r.stderr):
                    return p
            except Exception:
                pass
    for pat in [
        r"C:\Users\*\AppData\Local\Programs\Python\Python3*\python.exe",
        r"C:\Python3*\python.exe",
    ]:
        for exe in sorted(glob.glob(pat), reverse=True):
            return exe
    return ""


# ── Entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    os.chdir(INSTALL_DIR)
    app = WizardApp()
    app.mainloop()
