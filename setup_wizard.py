"""
setup_wizard.py — Assistente de instalação do Paçoca
Funciona em qualquer PC Windows sem Python instalado.
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
from tkinter import messagebox, ttk

BG     = "#0d1117"
BG2    = "#161b22"
BG3    = "#21262d"
FG     = "#c9d1d9"
FG2    = "#8b949e"
ACCENT = "#58a6ff"
GREEN  = "#3fb950"
RED    = "#f85149"
YELLOW = "#e3b341"
BORDER = "#30363d"


def _install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()


INSTALL_DIR = _install_dir()
PACOCA_EXE  = INSTALL_DIR / "Pacoca.exe"


def _creds_file() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = Path(meipass) / "core" / "credentials.json"
        if p.exists():
            return p
    return INSTALL_DIR / "core" / "credentials.json"


def _ollama_exe() -> str:
    """Retorna o caminho do executável ollama, ou '' se não encontrado."""
    w = shutil.which("ollama")
    if w:
        return w
    # Windows: Ollama instala em %LOCALAPPDATA%\Programs\Ollama\ (fora do PATH padrão)
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    if local.exists():
        return str(local)
    return ""


def _ollama_ok() -> bool:
    return bool(_ollama_exe())


def _token_ok() -> bool:
    return (INSTALL_DIR / "core" / "google_token.json").exists()


# ── Widgets ───────────────────────────────────────────────────────────

def _dot(parent, ok=None):
    color = GREEN if ok is True else (RED if ok is False else YELLOW)
    return tk.Label(parent, text="●", bg=BG, fg=color, font=("Segoe UI", 10))

def _h1(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=ACCENT, font=("Segoe UI", 17, "bold"))

def _h2(parent, text):
    return tk.Label(parent, text=text, bg=BG, fg=FG, font=("Segoe UI", 10, "bold"))

def _body(parent, text, color=FG2):
    return tk.Label(parent, text=text, bg=BG, fg=color,
                    font=("Segoe UI", 9), wraplength=470, justify="left")

def _btn(parent, text, cmd, color=ACCENT, width=14):
    return tk.Button(parent, text=text, command=cmd, bg=color, fg="white",
                     activebackground=color, relief="flat", padx=10, pady=6,
                     font=("Segoe UI", 9), width=width, cursor="hand2")


# ── App ───────────────────────────────────────────────────────────────

class Wizard(tk.Tk):
    PAGES = ["Boas-vindas", "Configuração", "Pronto!"]

    def __init__(self):
        super().__init__()
        self.title("Paçoca — Instalação")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("520x500")
        self._center()
        self._idx = 0
        self._frames: list = []
        self._build_chrome()
        self._build_pages()
        self._show(0)

    def _center(self):
        self.update_idletasks()
        w, h = 520, 500
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_chrome(self):
        hdr = tk.Frame(self, bg=BG2, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚡ PAÇOCA", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=20, pady=10)
        self._step_lbl = tk.Label(hdr, text="", bg=BG2, fg=FG2, font=("Segoe UI", 9))
        self._step_lbl.pack(side="right", padx=20)

        self._bar = ttk.Progressbar(self, length=520, mode="determinate",
                                     maximum=len(self.PAGES) - 1)
        s = ttk.Style(); s.theme_use("clam")
        s.configure("TProgressbar", troughcolor=BG3, background=ACCENT, thickness=4)
        self._bar.pack(fill="x")

        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True, padx=24, pady=16)

        nav = tk.Frame(self, bg=BG2, height=52)
        nav.pack(fill="x", side="bottom")
        nav.pack_propagate(False)
        self._back = _btn(nav, "← Voltar", self._go_back, BG3, 10)
        self._back.pack(side="left", padx=16, pady=10)
        self._next = _btn(nav, "Próximo →", self._go_next, width=12)
        self._next.pack(side="right", padx=16, pady=10)

    def _show(self, idx: int):
        for f in self._frames:
            f.pack_forget()
        self._frames[idx].pack(fill="both", expand=True)
        self._idx = idx
        self._bar["value"] = idx
        self._step_lbl.config(text=f"{idx + 1}/{len(self.PAGES)}  —  {self.PAGES[idx]}")
        self._back.config(state="normal" if idx > 0 else "disabled")
        last = idx == len(self.PAGES) - 1
        self._next.config(
            text="Fechar" if last else "Próximo →",
            command=self.destroy if last else self._go_next,
        )
        if hasattr(self._frames[idx], "_on_show"):
            self._frames[idx]._on_show()

    def _go_next(self):
        if self._idx < len(self.PAGES) - 1:
            self._show(self._idx + 1)

    def _go_back(self):
        if self._idx > 0:
            self._show(self._idx - 1)

    def _build_pages(self):
        self._frames = [
            self._page_welcome(),
            self._page_setup(),
            self._page_finish(),
        ]
        for f in self._frames:
            f.pack(fill="both", expand=True)
            f.pack_forget()

    # ── Página 1 — Boas-vindas ────────────────────────────────────────

    def _page_welcome(self):
        f = tk.Frame(self._content, bg=BG)
        _h1(f, "Bem-vindo ao Paçoca").pack(anchor="w", pady=(0, 4))
        _body(f, "Assistente pessoal de desktop — controle por voz ou texto, "
                 "100% local e gratuito.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        _h2(f, "Verificação do sistema").pack(anchor="w", pady=(0, 8))

        box = tk.Frame(f, bg=BG2, padx=12, pady=10)
        box.pack(fill="x")

        exe_ok = PACOCA_EXE.exists()
        items = [
            (f"Windows {platform.release()} "
             f"({'64-bit' if platform.machine().endswith('64') else '32-bit'})", True),
            (f"Pasta: {INSTALL_DIR}", True),
            (f"Pacoca.exe: {'encontrado' if exe_ok else 'NÃO encontrado — extraia o ZIP completo'}", exe_ok),
        ]
        for label, ok in items:
            row = tk.Frame(box, bg=BG2)
            row.pack(fill="x", pady=2)
            _dot(row, ok).pack(side="left")
            tk.Label(row, text=f"  {label}", bg=BG2, fg=FG if ok else YELLOW,
                     font=("Segoe UI", 9)).pack(side="left")

        if not exe_ok:
            tk.Frame(f, bg=BG, height=10).pack()
            _body(f,
                  "Pacoca.exe não está na mesma pasta que este instalador.\n"
                  "Extraia o ZIP completo e rode o Pacoca-Setup.exe de dentro da pasta extraída.",
                  YELLOW).pack(anchor="w")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=14)
        _body(f, "Próximas etapas (opcionais):\n"
                 "  • Instalar o Ollama para usar IA local\n"
                 "  • Fazer login com o Google (Calendar + Drive)").pack(anchor="w")
        return f

    # ── Página 2 — Setup ─────────────────────────────────────────────

    def _page_setup(self):
        f = tk.Frame(self._content, bg=BG)
        _h1(f, "Configuração").pack(anchor="w", pady=(0, 2))
        _body(f, "Tudo abaixo é opcional — pode pular e configurar depois.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=10)

        # Ollama
        _h2(f, "Ollama  (IA local)").pack(anchor="w", pady=(0, 4))
        sf = tk.Frame(f, bg=BG2, padx=12, pady=8)
        sf.pack(fill="x")
        self._ollama_dot = _dot(sf, _ollama_ok())
        self._ollama_dot.pack(side="left")
        self._ollama_lbl = tk.Label(sf,
            text=f"  Ollama {'instalado' if _ollama_ok() else 'não encontrado'}",
            bg=BG2, fg=FG, font=("Segoe UI", 9))
        self._ollama_lbl.pack(side="left")

        def _refresh_ollama():
            ok = _ollama_ok()
            color = GREEN if ok else RED
            text  = f"  Ollama {'instalado' if ok else 'não encontrado'}"
            try:
                self._ollama_dot.config(fg=color)
                self._ollama_lbl.config(text=text)
            except tk.TclError:
                pass

        or_ = tk.Frame(f, bg=BG)
        or_.pack(anchor="w", pady=(6, 0))
        _btn(or_, "Baixar Ollama",
             lambda: [webbrowser.open("https://ollama.com/download"), self.after(3000, _refresh_ollama)],
             width=14).pack(side="left")
        _btn(or_, "↺ Verificar", _refresh_ollama, BG3, 10).pack(side="left", padx=8)

        self._model_var = tk.StringVar(value="llama3")
        mr = tk.Frame(f, bg=BG)
        mr.pack(anchor="w", pady=(6, 0))
        tk.Label(mr, text="Modelo:", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(side="left")
        for m in ("llama3", "mistral", "phi3"):
            tk.Radiobutton(mr, text=m, variable=self._model_var, value=m,
                           bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                           font=("Segoe UI", 9)).pack(side="left", padx=6)

        self._model_bar    = ttk.Progressbar(f, length=460, mode="indeterminate")
        self._model_bar.pack(fill="x", pady=(6, 2))
        self._model_status = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8))
        self._model_status.pack(anchor="w")
        _btn(f, "⬇  Baixar modelo (~4 GB)", self._pull_model, width=22).pack(anchor="w", pady=(4, 8))

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=8)

        # Google
        _h2(f, "Google  (Calendar + Drive)").pack(anchor="w", pady=(0, 4))
        self._google_status = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8),
                                        wraplength=460, justify="left")
        self._google_status.pack(anchor="w", pady=(0, 4))

        gr = tk.Frame(f, bg=BG)
        gr.pack(anchor="w")
        self._google_dot = _dot(gr, _token_ok() if _token_ok() else None)
        self._google_dot.pack(side="left")
        tk.Label(gr, text="  Conta Google", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        _btn(gr, "  Fazer login  ", self._google_login, width=14).pack(side="left", padx=12)

        return f

    def _pull_model(self):
        exe = _ollama_exe()
        if not exe:
            messagebox.showerror("Ollama não encontrado",
                                 "Instale o Ollama em ollama.com/download e tente novamente.")
            return
        model = self._model_var.get()
        self._model_status.config(text=f"Baixando {model}… pode levar vários minutos.", fg=YELLOW)
        self._model_bar.start(12)

        def run():
            try:
                r = subprocess.run([exe, "pull", model], capture_output=True, text=True)
                ok = r.returncode == 0
                msg  = f"✓ {model} pronto." if ok else f"Erro: {r.stderr.strip() or 'falha ao baixar'}"
                color = GREEN if ok else RED
            except Exception as e:
                msg, color = f"Erro: {e}", RED
            self.after(0, lambda: self._model_bar.stop())
            self.after(0, lambda: self._model_status.config(text=msg, fg=color))

        threading.Thread(target=run, daemon=True).start()

    def _google_login(self):
        creds = _creds_file()
        if not creds.exists():
            self._google_status.config(
                text="credentials.json não encontrado no pacote.", fg=RED)
            return
        self._google_status.config(text="Abrindo navegador…", fg=YELLOW)
        SCOPES = [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.file",
        ]
        token_path = INSTALL_DIR / "core" / "google_token.json"
        with open(creds, encoding="utf-8") as _f:
            cfg = json.load(_f)

        def run():
            try:
                token_path.parent.mkdir(parents=True, exist_ok=True)
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_config(cfg, SCOPES)
                c = flow.run_local_server(port=0)
                token_path.write_text(c.to_json(), encoding="utf-8")
                def _on_ok():
                    self._google_dot.config(fg=GREEN)
                    self._google_status.config(text="✓ Conta Google conectada.", fg=GREEN)
                self.after(0, _on_ok)
            except Exception as e:
                self.after(0, lambda: self._google_status.config(
                    text=f"Erro: {e}", fg=RED))
        threading.Thread(target=run, daemon=True).start()

    # ── Página 3 — Pronto ─────────────────────────────────────────────

    def _page_finish(self):
        f = tk.Frame(self._content, bg=BG)
        f._on_show = lambda: self._render_finish(f)
        return f

    def _render_finish(self, f):
        for w in f.winfo_children():
            w.destroy()

        _h1(f, "Tudo pronto!").pack(anchor="w", pady=(0, 4))
        _body(f, "O Paçoca está instalado e configurado.").pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=12)

        for label, ok in [
            ("Pacoca.exe encontrado",   PACOCA_EXE.exists()),
            ("Ollama disponível",       _ollama_ok()),
            ("Google autorizado",       _token_ok()),
        ]:
            row = tk.Frame(f, bg=BG)
            row.pack(fill="x", pady=2)
            _dot(row, ok).pack(side="left")
            tk.Label(row, text=f"  {label}", bg=BG, fg=FG if ok else FG2,
                     font=("Segoe UI", 9)).pack(side="left")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=12)

        self._shortcut_lbl = tk.Label(f, text="", bg=BG, fg=FG2, font=("Segoe UI", 8))
        self._shortcut_lbl.pack(anchor="w", pady=(0, 8))

        # Cria atalho automaticamente
        self.after(200, self._auto_shortcut)

        br = tk.Frame(f, bg=BG)
        br.pack(anchor="w")
        _btn(br, "▶  Iniciar Paçoca", self._launch, width=16).pack(side="left")
        _btn(br, "🌐  Com dashboard", self._launch_web, "#1f5f2e", 16).pack(side="left", padx=8)

    def _auto_shortcut(self):
        if not PACOCA_EXE.exists():
            return
        try:
            desktop = Path.home() / "Desktop"
            bat = desktop / "Pacoca.lnk"
            try:
                import win32com.client  # type: ignore
                shell = win32com.client.Dispatch("WScript.Shell")
                lnk = shell.CreateShortCut(str(bat))
                lnk.TargetPath = str(PACOCA_EXE)
                lnk.WorkingDirectory = str(PACOCA_EXE.parent)
                lnk.Description = "Paçoca — Assistente pessoal"
                lnk.save()
            except Exception:
                # fallback .bat
                bat = desktop / "Pacoca.bat"
                bat.write_text(f'@echo off\nstart "" "{PACOCA_EXE}"\n', encoding="utf-8")
            self._shortcut_lbl.config(text="✓ Atalho criado na área de trabalho.", fg=GREEN)
        except Exception as e:
            self._shortcut_lbl.config(text=f"Atalho: {e}", fg=FG2)

    def _launch(self):
        if not PACOCA_EXE.exists():
            messagebox.showerror("Não encontrado", f"Pacoca.exe não encontrado em:\n{INSTALL_DIR}")
            return
        subprocess.Popen([str(PACOCA_EXE), "--mode", "text", "--no-tts"],
                         cwd=str(INSTALL_DIR),
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.destroy()

    def _launch_web(self):
        if not PACOCA_EXE.exists():
            messagebox.showerror("Não encontrado", f"Pacoca.exe não encontrado em:\n{INSTALL_DIR}")
            return
        subprocess.Popen([str(PACOCA_EXE), "--mode", "text", "--no-tts", "--web"],
                         cwd=str(INSTALL_DIR),
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.destroy()


if __name__ == "__main__":
    os.chdir(INSTALL_DIR)
    Wizard().mainloop()
