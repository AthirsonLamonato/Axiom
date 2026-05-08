"""
setup_wizard.py — Assistente de instalação visual do Axiom
Funciona em qualquer PC Windows — sem Python, sem pip install.
Axiom.exe já traz todas as dependências bundled.
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
AXIOM_EXE   = INSTALL_DIR / "Axiom" / "Axiom.exe"   # onedir build


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
    target  = str(AXIOM_EXE) if AXIOM_EXE.exists() else ""
    if not target:
        return

    bat = desktop / "Axiom.bat"
    bat.write_text(
        f'@echo off\nstart "" "{target}"\n',
        encoding="utf-8",
    )
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        lnk = shell.CreateShortCut(str(desktop / "Axiom.lnk"))
        lnk.TargetPath = target
        lnk.WorkingDirectory = str(AXIOM_EXE.parent)
        lnk.Description = "Axiom — Assistente pessoal inteligente"
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
        self.title("Axiom — Assistente de instalação")
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
        tk.Label(hdr, text="⚡ AXIOM", bg=BG2, fg=ACCENT,
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

    # ── Página 1 — Boas-vindas ────────────────────────────────────────

    def _page_welcome(self):
        f = styled_frame(self._content)
        h1(f, "Bem-vindo ao Axiom").pack(anchor="w", pady=(0, 4))
        body(f, "Assistente pessoal de desktop — controle por voz ou texto, "
                "100% local e gratuito. Sem pip install — tudo já está no executável.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        h2(f, "Verificação do sistema").pack(anchor="w", pady=(0, 8))

        info = tk.Frame(f, bg=BG2, padx=12, pady=10)
        info.pack(fill="x")

        axiom_ok = AXIOM_EXE.exists()
        for label, ok in [
            (f"Sistema: {platform.system()} {platform.release()} "
             f"({'64-bit' if platform.machine().endswith('64') else '32-bit'})", True),
            (f"Diretório: {INSTALL_DIR}", True),
            (f"Axiom.exe: {AXIOM_EXE}" if axiom_ok else "Axiom.exe: não encontrado", axiom_ok),
        ]:
            row = tk.Frame(info, bg=BG2)
            row.pack(fill="x", pady=2)
            status_dot(row, ok).pack(side="left")
            tk.Label(row, text=f"  {label}", bg=BG2, fg=FG,
                     font=("Segoe UI", 9)).pack(side="left")

        if not axiom_ok:
            warn = tk.Frame(f, bg=BG3, padx=12, pady=8)
            warn.pack(fill="x", pady=(8, 0))
            body(warn,
                 "Axiom.exe não encontrado. Certifique-se de que este wizard está na mesma "
                 "pasta que a pasta 'Axiom/' (o executável principal).\n\n"
                 "Estrutura esperada:\n"
                 "  📁 Axiom-v0.5.0-Windows/\n"
                 "    ▶ Axiom-Setup.exe   ← este arquivo\n"
                 "    📁 Axiom/\n"
                 "       ▶ Axiom.exe      ← executável principal", YELLOW).pack(anchor="w")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        body(f, "Este assistente irá:\n"
                "  1. Configurar o Ollama (IA local)\n"
                "  2. Ajustar suas preferências\n"
                "  3. Fazer login com o Google (Calendar + Drive)\n"
                "  4. Criar um atalho na área de trabalho").pack(anchor="w")
        return f

    # ── Página 2 — Ollama ─────────────────────────────────────────────

    def _page_ollama(self):
        f = styled_frame(self._content)
        h1(f, "Ollama & Modelo de IA").pack(anchor="w", pady=(0, 4))
        body(f, "O Axiom usa o Ollama para rodar um LLM local. "
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

        field("Picovoice access key:", self._cfg_wakekey, "(opcional — wake word 'Axiom')")

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
            "wake_word": {"access_key": self._cfg_wakekey.get()},
        }
        result = write_config_values(values)
        if result is True:
            self._cfg_status.config(text="✓ Configuração salva.", fg=GREEN)
        else:
            self._cfg_status.config(text=f"Erro: {result}", fg=RED)

    # ── Página 4 — Google Auth ────────────────────────────────────────

    def _page_google(self):
        f = styled_frame(self._content)
        h1(f, "Integração Google (opcional)").pack(anchor="w", pady=(0, 4))
        body(f, "Necessário para: ver agenda, criar eventos e backup no Google Drive. "
                "Pode pular — configure depois com 'axiom, autoriza calendário'.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        h2(f, "1. Criar credenciais OAuth").pack(anchor="w", pady=(0, 4))
        body(f, "• console.cloud.google.com → APIs & Services → Credenciais\n"
                "• Novo projeto → Ativar Calendar API e Drive API\n"
                "• Criar credenciais → OAuth 2.0 → Aplicativo desktop → Baixar JSON"
             ).pack(anchor="w", padx=8)
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

        self._google_status = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8))
        self._google_status.pack(anchor="w", pady=(8, 2))
        btn(f, "Conectar conta Google", self._run_google_auth, width=22).pack(anchor="w")
        body(f, "Uma janela do navegador abrirá para você fazer login.", FG2).pack(anchor="w", pady=(6, 0))
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
                text="Selecione um credentials.json válido primeiro.", fg=RED)
            return
        self._google_status.config(text="Abrindo navegador para autorização…", fg=YELLOW)

        SCOPES = [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.file",
        ]
        dest_creds = INSTALL_DIR / "core" / "credentials.json"
        token_path = INSTALL_DIR / "core" / "google_token.json"

        def run():
            try:
                dest_creds.parent.mkdir(parents=True, exist_ok=True)
                if Path(creds_src).resolve() != dest_creds.resolve():
                    shutil.copy2(creds_src, dest_creds)

                # Tenta importar direto (bundled no exe)
                try:
                    from google_auth_oauthlib.flow import InstalledAppFlow
                    flow = InstalledAppFlow.from_client_secrets_file(str(dest_creds), SCOPES)
                    creds = flow.run_local_server(port=0)
                    token_path.write_text(creds.to_json(), encoding="utf-8")
                except ImportError:
                    # Fallback: tenta via Python do sistema
                    exe = _find_system_python()
                    if not exe:
                        raise RuntimeError(
                            "google-auth-oauthlib não está disponível.\n"
                            "Execute o Axiom.exe uma vez e tente novamente.")
                    script = (
                        "from google_auth_oauthlib.flow import InstalledAppFlow\n"
                        "import json,sys\n"
                        "f=InstalledAppFlow.from_client_secrets_file(sys.argv[1],json.loads(sys.argv[2]))\n"
                        "c=f.run_local_server(port=0)\n"
                        "open(sys.argv[3],'w').write(c.to_json())\n"
                        "print('OK')\n"
                    )
                    r = subprocess.run(
                        [exe, "-c", script, str(dest_creds), json.dumps(SCOPES), str(token_path)],
                        capture_output=True, text=True, timeout=120,
                    )
                    if r.returncode != 0 or "OK" not in r.stdout:
                        raise RuntimeError(r.stderr.strip() or "Autorização cancelada.")

                def _ok():
                    self._cal_dot.config(fg=GREEN)
                    self._drv_dot.config(fg=GREEN)
                    self._cal_lbl.config(text="  Google Calendar  ✓")
                    self._drv_lbl.config(text="  Google Drive  ✓")
                    self._google_status.config(text="Conta Google conectada com sucesso.", fg=GREEN)

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
        body(f, "O Axiom está configurado e pronto para usar.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=12)

        cfg_path = _cfg_path()
        checks = [
            ("Axiom.exe encontrado",    AXIOM_EXE.exists()),
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
            if not AXIOM_EXE.exists():
                self._shortcut_status.config(text="Axiom.exe não encontrado.", fg=RED)
                return
            try:
                create_shortcut()
                self._shortcut_status.config(text="✓ Atalho criado na área de trabalho.", fg=GREEN)
            except Exception as e:
                self._shortcut_status.config(text=f"Erro: {e}", fg=RED)

        def launch():
            if not AXIOM_EXE.exists():
                messagebox.showerror("Axiom.exe não encontrado",
                                     f"Esperado em:\n{AXIOM_EXE}")
                return
            flags = subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0
            subprocess.Popen(
                [str(AXIOM_EXE), "--mode", "text", "--no-tts"],
                cwd=str(AXIOM_EXE.parent),
                creationflags=flags,
            )
            self.destroy()

        def launch_web():
            if not AXIOM_EXE.exists():
                messagebox.showerror("Axiom.exe não encontrado",
                                     f"Esperado em:\n{AXIOM_EXE}")
                return
            flags = subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0
            subprocess.Popen(
                [str(AXIOM_EXE), "--mode", "text", "--no-tts", "--web"],
                cwd=str(AXIOM_EXE.parent),
                creationflags=flags,
            )
            self.destroy()

        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(anchor="w", pady=4)
        btn(btn_row, "🖥  Criar atalho",    make_shortcut, color=BG3, width=14).pack(side="left")
        btn(btn_row, "▶  Iniciar Axiom",   launch, width=14).pack(side="left", padx=8)
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
