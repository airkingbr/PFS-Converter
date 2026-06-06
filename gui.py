import customtkinter as ctk
import subprocess
import threading
import os
import re
import sys
import json
import time
import shutil
import multiprocessing
from tkinter import filedialog

# Localiza arquivos embutidos (dentro do .exe ou ao lado do .py)
if getattr(sys, "frozen", False):
    _BUNDLE_DIR = sys._MEIPASS
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

_ICON_PATH = os.path.join(_BUNDLE_DIR, "icon.ico")

_PS1_PATH       = os.path.join(_BUNDLE_DIR, "New-OsfExfatImage.ps1")
_OSFMOUNT_SETUP = os.path.join(_BUNDLE_DIR, "osfmount_setup.exe")

# Quando frozen, usa o mkpfs_cli.exe embutido; caso contrário usa o mkpfs do PATH
if getattr(sys, "frozen", False):
    _MKPFS = os.path.join(_BUNDLE_DIR, "mkpfs_cli.exe")
else:
    _MKPFS = "mkpfs"

# Caminhos padrão onde o OSFMount pode estar instalado
_OSFMOUNT_CANDIDATES = [
    r"C:\Program Files\OSFMount\osfmount.com",
    r"C:\Program Files (x86)\OSFMount\osfmount.com",
    r"C:\Program Files\PassMark\OSFMount\osfmount.com",
    r"C:\Program Files (x86)\PassMark\OSFMount\osfmount.com",
]

def _find_osfmount() -> str | None:
    for p in _OSFMOUNT_CANDIDATES:
        if os.path.isfile(p):
            return p
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(folder, "osfmount.com")
        if os.path.isfile(candidate):
            return candidate
    return None

# Regex progresso mkpfs: [###---]  45% scan
_RE_PROGRESS = re.compile(r"\[[#\-]+\]\s+(\d+)%\s+(\w+)")
# Regex etapas PS1: [1/4], [2/4] ...
_RE_PS1_STEP = re.compile(r"\[(\d+)/(\d+)\]")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VERSION = "0.0.2"

CONFIG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PFS Converter", "config.json")


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(data: dict):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"PFS Converter v{VERSION}")
        self.geometry("720x740")
        self.resizable(False, False)
        if os.path.isfile(_ICON_PATH):
            self.iconbitmap(_ICON_PATH)

        self._cpu_count = multiprocessing.cpu_count()
        self._active_proc = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        cfg = _load_config()
        self._saved_cpus = int(cfg.get("cpu_count", self._cpu_count))

        # Tab 1 — Dump > ffpfsc
        self._t1_input_folder = ctk.StringVar()
        self._t1_temp_file    = ctk.StringVar(value=cfg.get("temp_file", ""))
        self._t1_output_file  = ctk.StringVar(value=cfg.get("t1_output_dir", ""))

        # Tab 2 — exfat > ffpfsc
        self._t2_source_file  = ctk.StringVar()
        self._t2_output_file  = ctk.StringVar(value=cfg.get("t2_output_dir", ""))

        # Tab 3 — Dump > exfat
        self._t3_input_folder = ctk.StringVar()
        self._t3_output_file  = ctk.StringVar(value=cfg.get("t3_output_dir", ""))

        # Tab 4 — Dump > exfat > ffpfsc
        self._t4_input_folder = ctk.StringVar()
        self._t4_temp_folder  = ctk.StringVar(value=cfg.get("t4_temp_folder", ""))
        self._t4_output_file  = ctk.StringVar(value=cfg.get("t4_output_dir", ""))

        self._build_ui()

        # Instala OSFMount silenciosamente se não estiver presente
        if not _find_osfmount():
            threading.Thread(target=self._auto_install_osfmount, daemon=True).start()

    # ──────────────────────────────────────────────────────────
    #  UI principal
    # ──────────────────────────────────────────────────────────
    def _build_ui(self):
        ctk.CTkLabel(self, text="🎮  PFS Converter",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 4))
        ctk.CTkLabel(self, text=f"v{VERSION}",
                     font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(0, 10))

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._tabs.add("Dump > ffpfsc")
        self._tabs.add("exfat > ffpfsc")
        self._tabs.add("Dump > exfat")
        self._tabs.add("Dump > exfat > ffpfsc")

        self._build_tab1(self._tabs.tab("Dump > ffpfsc"))
        self._build_tab2(self._tabs.tab("exfat > ffpfsc"))
        self._build_tab3(self._tabs.tab("Dump > exfat"))
        self._build_tab4(self._tabs.tab("Dump > exfat > ffpfsc"))

    # ──────────────────────────────────────────────────────────
    #  Tab 1 — Dump > ffpfsc
    # ──────────────────────────────────────────────────────────
    def _build_tab1(self, parent):
        pad = {"padx": 16, "pady": (8, 0)}

        self._tab_section(parent, "Passo 1 — Dump de entrada")
        r1 = ctk.CTkFrame(parent, fg_color="transparent")
        r1.pack(fill="x", **pad)
        ctk.CTkEntry(r1, textvariable=self._t1_input_folder,
                     placeholder_text="Selecione o dump...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r1, text="Selecionar", width=110,
                      command=self._t1_pick_folder).pack(side="left")

        self._tab_section(parent, "Passo 2 — Arquivo temporário (pfs_image.dat)")
        r2 = ctk.CTkFrame(parent, fg_color="transparent")
        r2.pack(fill="x", **pad)
        ctk.CTkEntry(r2, textvariable=self._t1_temp_file,
                     placeholder_text="Onde salvar pfs_image.dat...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r2, text="Selecionar", width=110,
                      command=self._t1_pick_temp).pack(side="left")

        self._tab_section(parent, "Passo 3 — Arquivo de saída (.ffpfsc)")
        r3 = ctk.CTkFrame(parent, fg_color="transparent")
        r3.pack(fill="x", **pad)
        ctk.CTkEntry(r3, textvariable=self._t1_output_file,
                     placeholder_text="Nome e local do arquivo final .ffpfsc...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r3, text="Selecionar", width=110,
                      command=self._t1_pick_output).pack(side="left")

        self._tab_section(parent, "Núcleos de CPU")
        cpu_row = ctk.CTkFrame(parent, fg_color="transparent")
        cpu_row.pack(fill="x", padx=16, pady=(4, 0))
        self._t1_cpu_label = ctk.CTkLabel(cpu_row, text=f"{self._saved_cpus} / {self._cpu_count}", width=60)
        self._t1_cpu_label.pack(side="right")
        self._t1_cpu_slider = ctk.CTkSlider(cpu_row, from_=1, to=self._cpu_count,
                                             number_of_steps=self._cpu_count - 1,
                                             command=self._on_cpu_slider)
        self._t1_cpu_slider.set(self._saved_cpus)
        self._t1_cpu_slider.pack(side="left", fill="x", expand=True, padx=(0, 12))

        self._t1_btn = ctk.CTkButton(parent, text="Converter", height=40,
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     command=self._t1_start)
        self._t1_btn.pack(pady=(14, 0), padx=16, fill="x")

        self._t1_phase_label = ctk.CTkLabel(parent, text="", anchor="w", font=ctk.CTkFont(size=12))
        self._t1_phase_label.pack(fill="x", padx=16, pady=(10, 2))
        self._t1_bar = ctk.CTkProgressBar(parent, height=18)
        self._t1_bar.set(0)
        self._t1_bar.pack(fill="x", padx=16)

        ctk.CTkLabel(parent, text="Log", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self._t1_log = ctk.CTkTextbox(parent, height=200, font=ctk.CTkFont(family="Courier New", size=11), state="disabled")
        self._t1_log.pack(fill="both", expand=True, padx=16, pady=(0, 10))

    # ──────────────────────────────────────────────────────────
    #  Tab 2 — exfat > ffpfsc
    # ──────────────────────────────────────────────────────────
    def _build_tab2(self, parent):
        pad = {"padx": 16, "pady": (8, 0)}

        self._tab_section(parent, "Arquivo de origem (.exfat)")
        r1 = ctk.CTkFrame(parent, fg_color="transparent")
        r1.pack(fill="x", **pad)
        ctk.CTkEntry(r1, textvariable=self._t2_source_file,
                     placeholder_text="Selecione o arquivo .exfat...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r1, text="Selecionar", width=110,
                      command=self._t2_pick_source).pack(side="left")

        self._tab_section(parent, "Arquivo de saída (.ffpfsc)")
        r2 = ctk.CTkFrame(parent, fg_color="transparent")
        r2.pack(fill="x", **pad)
        ctk.CTkEntry(r2, textvariable=self._t2_output_file,
                     placeholder_text="Nome e local do arquivo final .ffpfsc...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r2, text="Selecionar", width=110,
                      command=self._t2_pick_output).pack(side="left")

        self._tab_section(parent, "Núcleos de CPU")
        cpu_row = ctk.CTkFrame(parent, fg_color="transparent")
        cpu_row.pack(fill="x", padx=16, pady=(4, 0))
        self._t2_cpu_label = ctk.CTkLabel(cpu_row, text=f"{self._saved_cpus} / {self._cpu_count}", width=60)
        self._t2_cpu_label.pack(side="right")
        self._t2_cpu_slider = ctk.CTkSlider(cpu_row, from_=1, to=self._cpu_count,
                                             number_of_steps=self._cpu_count - 1,
                                             command=self._on_cpu_slider)
        self._t2_cpu_slider.set(self._saved_cpus)
        self._t2_cpu_slider.pack(side="left", fill="x", expand=True, padx=(0, 12))

        self._t2_btn = ctk.CTkButton(parent, text="Converter", height=40,
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     command=self._t2_start)
        self._t2_btn.pack(pady=(14, 0), padx=16, fill="x")

        self._t2_phase_label = ctk.CTkLabel(parent, text="", anchor="w", font=ctk.CTkFont(size=12))
        self._t2_phase_label.pack(fill="x", padx=16, pady=(10, 2))
        self._t2_bar = ctk.CTkProgressBar(parent, height=18)
        self._t2_bar.set(0)
        self._t2_bar.pack(fill="x", padx=16)

        ctk.CTkLabel(parent, text="Log", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self._t2_log = ctk.CTkTextbox(parent, height=200, font=ctk.CTkFont(family="Courier New", size=11), state="disabled")
        self._t2_log.pack(fill="both", expand=True, padx=16, pady=(0, 10))

    # ──────────────────────────────────────────────────────────
    #  Tab 3 — Dump > exfat
    # ──────────────────────────────────────────────────────────
    def _build_tab3(self, parent):
        pad = {"padx": 16, "pady": (8, 0)}

        osf_row = ctk.CTkFrame(parent, fg_color="transparent")
        osf_row.pack(fill="x", padx=16, pady=(10, 0))
        osf = _find_osfmount()
        self._t3_osf_label = ctk.CTkLabel(osf_row,
                                           text="✓ OSFMount instalado" if osf else "✗ OSFMount não encontrado",
                                           anchor="w", text_color="#a3e635" if osf else "#f87171",
                                           font=ctk.CTkFont(size=11))
        self._t3_osf_label.pack(side="left")
        if not osf:
            ctk.CTkButton(osf_row, text="Instalar OSFMount", width=150, height=26,
                          command=self._install_osfmount_manual).pack(side="right")

        self._tab_section(parent, "Dump de entrada")
        r1 = ctk.CTkFrame(parent, fg_color="transparent")
        r1.pack(fill="x", **pad)
        ctk.CTkEntry(r1, textvariable=self._t3_input_folder,
                     placeholder_text="Selecione o dump...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r1, text="Selecionar", width=110,
                      command=self._t3_pick_folder).pack(side="left")

        self._tab_section(parent, "Arquivo de saída (.exfat)")
        r2 = ctk.CTkFrame(parent, fg_color="transparent")
        r2.pack(fill="x", **pad)
        ctk.CTkEntry(r2, textvariable=self._t3_output_file,
                     placeholder_text="Nome e local do arquivo .exfat...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r2, text="Selecionar", width=110,
                      command=self._t3_pick_output).pack(side="left")

        self._t3_btn = ctk.CTkButton(parent, text="Converter", height=40,
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     command=self._t3_start)
        self._t3_btn.pack(pady=(18, 0), padx=16, fill="x")

        self._t3_phase_label = ctk.CTkLabel(parent, text="", anchor="w", font=ctk.CTkFont(size=12))
        self._t3_phase_label.pack(fill="x", padx=16, pady=(10, 2))
        self._t3_bar = ctk.CTkProgressBar(parent, height=18)
        self._t3_bar.set(0)
        self._t3_bar.pack(fill="x", padx=16)

        ctk.CTkLabel(parent, text="Log", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self._t3_log = ctk.CTkTextbox(parent, height=200, font=ctk.CTkFont(family="Courier New", size=11), state="disabled")
        self._t3_log.pack(fill="both", expand=True, padx=16, pady=(0, 10))

    # ──────────────────────────────────────────────────────────
    #  Tab 4 — Dump > exfat > ffpfsc
    # ──────────────────────────────────────────────────────────
    def _build_tab4(self, parent):
        pad = {"padx": 16, "pady": (8, 0)}

        osf_row = ctk.CTkFrame(parent, fg_color="transparent")
        osf_row.pack(fill="x", padx=16, pady=(10, 0))
        osf = _find_osfmount()
        self._t4_osf_label = ctk.CTkLabel(osf_row,
                                           text="✓ OSFMount instalado" if osf else "✗ OSFMount não encontrado",
                                           anchor="w", text_color="#a3e635" if osf else "#f87171",
                                           font=ctk.CTkFont(size=11))
        self._t4_osf_label.pack(side="left")

        self._tab_section(parent, "Dump de entrada")
        r1 = ctk.CTkFrame(parent, fg_color="transparent")
        r1.pack(fill="x", **pad)
        ctk.CTkEntry(r1, textvariable=self._t4_input_folder,
                     placeholder_text="Selecione o dump...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r1, text="Selecionar", width=110,
                      command=self._t4_pick_folder).pack(side="left")

        self._tab_section(parent, "Pasta para arquivos temporários")
        r2 = ctk.CTkFrame(parent, fg_color="transparent")
        r2.pack(fill="x", **pad)
        ctk.CTkEntry(r2, textvariable=self._t4_temp_folder,
                     placeholder_text="Onde salvar o .exfat e .dat temporários...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r2, text="Selecionar", width=110,
                      command=self._t4_pick_temp_folder).pack(side="left")

        self._tab_section(parent, "Arquivo de saída (.ffpfsc)")
        r3 = ctk.CTkFrame(parent, fg_color="transparent")
        r3.pack(fill="x", **pad)
        ctk.CTkEntry(r3, textvariable=self._t4_output_file,
                     placeholder_text="Nome e local do arquivo final .ffpfsc...",
                     width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r3, text="Selecionar", width=110,
                      command=self._t4_pick_output).pack(side="left")

        self._tab_section(parent, "Núcleos de CPU")
        cpu_row = ctk.CTkFrame(parent, fg_color="transparent")
        cpu_row.pack(fill="x", padx=16, pady=(4, 0))
        self._t4_cpu_label = ctk.CTkLabel(cpu_row, text=f"{self._saved_cpus} / {self._cpu_count}", width=60)
        self._t4_cpu_label.pack(side="right")
        self._t4_cpu_slider = ctk.CTkSlider(cpu_row, from_=1, to=self._cpu_count,
                                             number_of_steps=self._cpu_count - 1,
                                             command=self._on_cpu_slider)
        self._t4_cpu_slider.set(self._saved_cpus)
        self._t4_cpu_slider.pack(side="left", fill="x", expand=True, padx=(0, 12))

        self._t4_btn = ctk.CTkButton(parent, text="Converter", height=40,
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     command=self._t4_start)
        self._t4_btn.pack(pady=(14, 0), padx=16, fill="x")

        self._t4_phase_label = ctk.CTkLabel(parent, text="", anchor="w", font=ctk.CTkFont(size=12))
        self._t4_phase_label.pack(fill="x", padx=16, pady=(10, 2))
        self._t4_bar = ctk.CTkProgressBar(parent, height=18)
        self._t4_bar.set(0)
        self._t4_bar.pack(fill="x", padx=16)

        ctk.CTkLabel(parent, text="Log", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self._t4_log = ctk.CTkTextbox(parent, height=200, font=ctk.CTkFont(family="Courier New", size=11), state="disabled")
        self._t4_log.pack(fill="both", expand=True, padx=16, pady=(0, 10))

    def _tab_section(self, parent, title):
        ctk.CTkLabel(parent, text=title, anchor="w",
                     font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=16, pady=(12, 2))

    # ──────────────────────────────────────────────────────────
    #  CPU slider (sincronizado entre tabs)
    # ──────────────────────────────────────────────────────────
    def _on_cpu_slider(self, value):
        cpus = int(value)
        for lbl in (self._t1_cpu_label, self._t2_cpu_label, self._t4_cpu_label):
            lbl.configure(text=f"{cpus} / {self._cpu_count}")
        for sl in (self._t1_cpu_slider, self._t2_cpu_slider, self._t4_cpu_slider):
            sl.set(cpus)
        _save_config({**_load_config(), "cpu_count": cpus})

    # ──────────────────────────────────────────────────────────
    #  OSFMount — instalação
    # ──────────────────────────────────────────────────────────
    def _auto_install_osfmount(self):
        if not os.path.isfile(_OSFMOUNT_SETUP):
            return
        for lbl in (self._t3_osf_label, self._t4_osf_label):
            self.after(0, lambda l=lbl: l.configure(text="⏳ Instalando OSFMount...", text_color="white"))
        try:
            proc = subprocess.Popen(
                [_OSFMOUNT_SETUP, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            proc.wait()
            if _find_osfmount():
                for lbl in (self._t3_osf_label, self._t4_osf_label):
                    self.after(0, lambda l=lbl: l.configure(text="✓ OSFMount instalado com sucesso!", text_color="#a3e635"))
            else:
                for lbl in (self._t3_osf_label, self._t4_osf_label):
                    self.after(0, lambda l=lbl: l.configure(text="✗ Instalação falhou. Tente manualmente.", text_color="#f87171"))
        except Exception as e:
            for lbl in (self._t3_osf_label, self._t4_osf_label):
                self.after(0, lambda l=lbl: l.configure(text=f"✗ Erro: {e}", text_color="#f87171"))

    def _install_osfmount_manual(self):
        if not os.path.isfile(_OSFMOUNT_SETUP):
            self._t3_osf_label.configure(text="✗ Instalador não encontrado.", text_color="#f87171")
            return
        self._t3_osf_label.configure(text="⏳ Instalando OSFMount...", text_color="white")
        threading.Thread(target=self._auto_install_osfmount, daemon=True).start()

    # ──────────────────────────────────────────────────────────
    #  Tab 1 — pickers
    # ──────────────────────────────────────────────────────────
    def _t1_pick_folder(self):
        path = filedialog.askdirectory(title="Selecione o dump")
        if path:
            self._t1_input_folder.set(path)
            name = os.path.basename(path.rstrip("/\\"))
            if not self._t1_temp_file.get():
                self._t1_temp_file.set(os.path.join(path, "pfs_image.dat"))
            out_dir = os.path.dirname(self._t1_output_file.get()) if self._t1_output_file.get() else path
            self._t1_output_file.set(os.path.join(out_dir, f"{name}.ffpfsc"))

    def _t1_pick_temp(self):
        current = self._t1_temp_file.get()
        path = filedialog.asksaveasfilename(
            title="Local do arquivo temporário",
            defaultextension=".dat",
            filetypes=[("DAT file", "*.dat"), ("All files", "*.*")],
            initialfile="pfs_image.dat",
            initialdir=os.path.dirname(current) if current else None,
        )
        if path:
            self._t1_temp_file.set(path)
            _save_config({**_load_config(), "temp_file": path})

    def _t1_pick_output(self):
        current = self._t1_output_file.get()
        path = filedialog.asksaveasfilename(
            title="Salvar arquivo final como",
            defaultextension=".ffpfsc",
            filetypes=[("FFPFSC file", "*.ffpfsc")],
            initialdir=os.path.dirname(current) if current else None,
        )
        if path:
            if not path.endswith(".ffpfsc"):
                path = os.path.splitext(path)[0] + ".ffpfsc"
            self._t1_output_file.set(path)
            _save_config({**_load_config(), "t1_output_dir": os.path.dirname(path)})

    # ──────────────────────────────────────────────────────────
    #  Tab 2 — pickers
    # ──────────────────────────────────────────────────────────
    def _t2_pick_source(self):
        current = self._t2_source_file.get()
        path = filedialog.askopenfilename(
            title="Selecione o arquivo .exfat",
            filetypes=[("exFAT file", "*.exfat"), ("All files", "*.*")],
            initialdir=os.path.dirname(current) if current else None,
        )
        if path:
            self._t2_source_file.set(path)
            base = os.path.splitext(os.path.basename(path))[0]
            out_dir = os.path.dirname(self._t2_output_file.get()) if self._t2_output_file.get() else os.path.dirname(path)
            self._t2_output_file.set(os.path.join(out_dir, f"{base}.ffpfsc"))

    def _t2_pick_output(self):
        current = self._t2_output_file.get()
        path = filedialog.asksaveasfilename(
            title="Salvar arquivo final como",
            defaultextension=".ffpfsc",
            filetypes=[("FFPFSC file", "*.ffpfsc")],
            initialdir=os.path.dirname(current) if current else None,
        )
        if path:
            if not path.endswith(".ffpfsc"):
                path = os.path.splitext(path)[0] + ".ffpfsc"
            self._t2_output_file.set(path)
            _save_config({**_load_config(), "t2_output_dir": os.path.dirname(path)})

    # ──────────────────────────────────────────────────────────
    #  Tab 3 — pickers
    # ──────────────────────────────────────────────────────────
    def _t3_pick_folder(self):
        path = filedialog.askdirectory(title="Selecione o dump")
        if path:
            self._t3_input_folder.set(path)
            name = os.path.basename(path.rstrip("/\\"))
            out_dir = os.path.dirname(self._t3_output_file.get()) if self._t3_output_file.get() else path
            self._t3_output_file.set(os.path.join(out_dir, f"{name}.exfat"))

    def _t3_pick_output(self):
        current = self._t3_output_file.get()
        path = filedialog.asksaveasfilename(
            title="Salvar arquivo .exfat como",
            defaultextension=".exfat",
            filetypes=[("exFAT image", "*.exfat"), ("All files", "*.*")],
            initialdir=os.path.dirname(current) if current else None,
        )
        if path:
            if not path.endswith(".exfat"):
                path = os.path.splitext(path)[0] + ".exfat"
            self._t3_output_file.set(path)
            _save_config({**_load_config(), "t3_output_dir": os.path.dirname(path)})

    # ──────────────────────────────────────────────────────────
    #  Tab 4 — pickers
    # ──────────────────────────────────────────────────────────
    def _t4_pick_folder(self):
        path = filedialog.askdirectory(title="Selecione o dump")
        if path:
            self._t4_input_folder.set(path)
            name = os.path.basename(path.rstrip("/\\"))
            out_dir = os.path.dirname(self._t4_output_file.get()) if self._t4_output_file.get() else path
            self._t4_output_file.set(os.path.join(out_dir, f"{name}.ffpfsc"))

    def _t4_pick_temp_folder(self):
        path = filedialog.askdirectory(title="Selecione a pasta para arquivos temporários")
        if path:
            self._t4_temp_folder.set(path)
            _save_config({**_load_config(), "t4_temp_folder": path})

    def _t4_pick_output(self):
        current = self._t4_output_file.get()
        path = filedialog.asksaveasfilename(
            title="Salvar arquivo final como",
            defaultextension=".ffpfsc",
            filetypes=[("FFPFSC file", "*.ffpfsc")],
            initialdir=os.path.dirname(current) if current else None,
        )
        if path:
            if not path.endswith(".ffpfsc"):
                path = os.path.splitext(path)[0] + ".ffpfsc"
            self._t4_output_file.set(path)
            _save_config({**_load_config(), "t4_output_dir": os.path.dirname(path)})

    # ──────────────────────────────────────────────────────────
    #  Tab 1 — conversão
    # ──────────────────────────────────────────────────────────
    def _t1_start(self):
        folder = self._t1_input_folder.get().strip()
        temp   = self._t1_temp_file.get().strip()
        output = self._t1_output_file.get().strip()
        if not folder or not os.path.isdir(folder):
            self._log_append(self._t1_log, "[ERRO] Selecione um dump válido.\n", clear=True); return
        if not temp:
            self._log_append(self._t1_log, "[ERRO] Informe o caminho do arquivo temporário.\n", clear=True); return
        if not output:
            self._log_append(self._t1_log, "[ERRO] Informe o caminho do arquivo de saída.\n", clear=True); return
        cpus = int(self._t1_cpu_slider.get())
        self._t1_btn.configure(state="disabled", text="Convertendo...")
        self._t1_bar.set(0); self._t1_phase_label.configure(text="")
        self._log_clear(self._t1_log)
        self._t1_start_time = time.time()
        threading.Thread(target=self._t1_run, args=(folder, temp, output, cpus), daemon=True).start()

    def _t1_run(self, folder, temp, output, cpus):
        if os.path.exists(temp): os.remove(temp)
        if os.path.exists(output): os.remove(output)
        cmd1 = [_MKPFS, "pack", "folder", "--no-compress", "--no-adjust-output-file-extension",
                "--version", "PS5", "--inode-bits", "32", "--cpu-count", str(cpus), folder, temp]
        staging_dir = os.path.join(os.path.dirname(os.path.abspath(temp)), "_mkpfs_staging")
        os.makedirs(staging_dir, exist_ok=True)
        cmd2 = [_MKPFS, "pack", "file", "--version", "PS5", "--inode-bits", "32",
                "--cpu-count", str(cpus), "--temp-folder", staging_dir, temp, output]
        success = self._run_cmd(cmd1, self._t1_bar, self._t1_phase_label, self._t1_log, "Passo 1/2")
        if success:
            success = self._run_cmd(cmd2, self._t1_bar, self._t1_phase_label, self._t1_log, "Passo 2/2")
        if os.path.exists(temp):
            try: os.remove(temp)
            except: pass
        shutil.rmtree(staging_dir, ignore_errors=True)
        self._finish(self._t1_phase_label, self._t1_btn, self._t1_start_time, success)

    # ──────────────────────────────────────────────────────────
    #  Tab 2 — conversão
    # ──────────────────────────────────────────────────────────
    def _t2_start(self):
        source = self._t2_source_file.get().strip()
        output = self._t2_output_file.get().strip()
        if not source or not os.path.isfile(source):
            self._log_append(self._t2_log, "[ERRO] Selecione um arquivo .exfat válido.\n", clear=True); return
        if not output:
            self._log_append(self._t2_log, "[ERRO] Informe o caminho do arquivo de saída.\n", clear=True); return
        cpus = int(self._t2_cpu_slider.get())
        self._t2_btn.configure(state="disabled", text="Convertendo...")
        self._t2_bar.set(0); self._t2_phase_label.configure(text="")
        self._log_clear(self._t2_log)
        self._t2_start_time = time.time()
        threading.Thread(target=self._t2_run, args=(source, output, cpus), daemon=True).start()

    def _t2_run(self, source, output, cpus):
        if os.path.exists(output): os.remove(output)
        staging_dir = os.path.join(os.path.dirname(os.path.abspath(source)), "_mkpfs_staging")
        os.makedirs(staging_dir, exist_ok=True)
        cmd = [_MKPFS, "pack", "file", "--version", "PS5", "--inode-bits", "32",
               "--cpu-count", str(cpus), "--temp-folder", staging_dir, source, output]
        success = self._run_cmd(cmd, self._t2_bar, self._t2_phase_label, self._t2_log, "")
        shutil.rmtree(staging_dir, ignore_errors=True)
        self._finish(self._t2_phase_label, self._t2_btn, self._t2_start_time, success)

    # ──────────────────────────────────────────────────────────
    #  Tab 3 — conversão
    # ──────────────────────────────────────────────────────────
    def _t3_start(self):
        folder = self._t3_input_folder.get().strip()
        output = self._t3_output_file.get().strip()
        if not folder or not os.path.isdir(folder):
            self._log_append(self._t3_log, "[ERRO] Selecione um dump válido.\n", clear=True); return
        if not output:
            self._log_append(self._t3_log, "[ERRO] Informe o caminho do arquivo de saída.\n", clear=True); return
        if not _find_osfmount():
            self._log_append(self._t3_log, "[ERRO] OSFMount não encontrado.\n", clear=True); return
        self._t3_btn.configure(state="disabled", text="Convertendo...")
        self._t3_bar.set(0); self._t3_phase_label.configure(text="")
        self._log_clear(self._t3_log)
        self._t3_start_time = time.time()
        threading.Thread(target=self._t3_run, args=(folder, output), daemon=True).start()

    def _t3_run(self, folder, output):
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", _PS1_PATH, "-ImagePath", output, "-SourceDir", folder, "-ForceOverwrite"]
        success = self._run_cmd_ps1(cmd, self._t3_bar, self._t3_phase_label, self._t3_log)
        self._finish(self._t3_phase_label, self._t3_btn, self._t3_start_time, success)

    # ──────────────────────────────────────────────────────────
    #  Tab 4 — conversão Dump > exfat > ffpfsc
    # ──────────────────────────────────────────────────────────
    def _t4_start(self):
        folder  = self._t4_input_folder.get().strip()
        tmp_dir = self._t4_temp_folder.get().strip()
        output  = self._t4_output_file.get().strip()
        if not folder or not os.path.isdir(folder):
            self._log_append(self._t4_log, "[ERRO] Selecione um dump válido.\n", clear=True); return
        if not tmp_dir:
            self._log_append(self._t4_log, "[ERRO] Informe a pasta para arquivos temporários.\n", clear=True); return
        if not output:
            self._log_append(self._t4_log, "[ERRO] Informe o caminho do arquivo de saída.\n", clear=True); return
        if not _find_osfmount():
            self._log_append(self._t4_log, "[ERRO] OSFMount não encontrado.\n", clear=True); return
        cpus = int(self._t4_cpu_slider.get())
        self._t4_btn.configure(state="disabled", text="Convertendo...")
        self._t4_bar.set(0); self._t4_phase_label.configure(text="")
        self._log_clear(self._t4_log)
        self._t4_start_time = time.time()
        threading.Thread(target=self._t4_run, args=(folder, tmp_dir, output, cpus), daemon=True).start()

    def _t4_run(self, folder, tmp_dir, output, cpus):
        name = os.path.basename(folder.rstrip("/\\"))
        os.makedirs(tmp_dir, exist_ok=True)

        # .exfat temporário na pasta escolhida pelo usuário (nunca dentro do dump)
        exfat_tmp = os.path.join(tmp_dir, f"{name}.exfat")

        # Passo 1: Dump > exfat
        self.after(0, lambda: self._t4_phase_label.configure(
            text="Passo 1/2 — Criando imagem exFAT...", text_color="white"))
        cmd_ps1 = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", _PS1_PATH, "-ImagePath", exfat_tmp,
                   "-SourceDir", folder, "-ForceOverwrite"]
        success = self._run_cmd_ps1(cmd_ps1, self._t4_bar, self._t4_phase_label,
                                     self._t4_log, step_offset=0, total_steps=2)

        if success:
            # Passo 2: exfat > ffpfsc
            if os.path.exists(output): os.remove(output)
            staging_dir = os.path.join(tmp_dir, "_mkpfs_staging")
            os.makedirs(staging_dir, exist_ok=True)
            cmd_mkpfs = [_MKPFS, "pack", "file", "--version", "PS5", "--inode-bits", "32",
                         "--cpu-count", str(cpus), "--temp-folder", staging_dir, exfat_tmp, output]
            success = self._run_cmd(cmd_mkpfs, self._t4_bar, self._t4_phase_label,
                                     self._t4_log, "Passo 2/2")
            shutil.rmtree(staging_dir, ignore_errors=True)

        # Limpa .exfat temporário
        if os.path.exists(exfat_tmp):
            try: os.remove(exfat_tmp)
            except: pass

        self._finish(self._t4_phase_label, self._t4_btn, self._t4_start_time, success)

    # ──────────────────────────────────────────────────────────
    #  Core: mkpfs — separa progresso do log
    # ──────────────────────────────────────────────────────────
    def _run_cmd(self, cmd, bar, phase_label, log, step_prefix) -> bool:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            self._active_proc = proc
            for line in proc.stdout:
                m = _RE_PROGRESS.search(line)
                if m:
                    pct   = int(m.group(1)) / 100.0
                    phase = m.group(2).capitalize()
                    txt   = f"{step_prefix} — {phase}  {int(pct*100)}%" if step_prefix else f"{phase}  {int(pct*100)}%"
                    self.after(0, lambda v=pct, t=txt: (bar.set(v), phase_label.configure(text=t, text_color="white")))
                else:
                    s = line.rstrip("\n")
                    if s: self.after(0, lambda l=s: self._log_append(log, l + "\n"))
            proc.stdout.close(); proc.wait()
            self._active_proc = None
            return proc.returncode == 0
        except FileNotFoundError:
            self.after(0, lambda: self._log_append(log, f"[ERRO] mkpfs não encontrado: {_MKPFS}\n"))
            return False
        except Exception as e:
            self.after(0, lambda: self._log_append(log, f"[ERRO] {e}\n"))
            return False

    # ──────────────────────────────────────────────────────────
    #  Core: PowerShell PS1 — parseia [N/Total] para a barra
    # ──────────────────────────────────────────────────────────
    def _run_cmd_ps1(self, cmd, bar, phase_label, log,
                     step_offset=0, total_steps=1) -> bool:
        step_labels = {
            1: "Criando e montando imagem...",
            2: "Formatando exFAT...",
            3: "Copiando arquivos...",
            4: "Desmontando volume...",
        }
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            self._active_proc = proc
            for line in proc.stdout:
                s = line.rstrip("\n")
                if not s: continue
                m = _RE_PS1_STEP.search(s)
                if m:
                    step  = int(m.group(1))
                    total = int(m.group(2))
                    # Se usado como sub-passo (total_steps=2), mapeia 0..0.5 ou 0.5..1
                    pct = (step_offset + step / total) / total_steps
                    lbl = step_labels.get(step, s)
                    if total_steps > 1:
                        lbl = f"Passo 1/2 — {lbl}"
                    self.after(0, lambda v=pct, t=lbl: (bar.set(v), phase_label.configure(text=t, text_color="white")))
                self.after(0, lambda l=s: self._log_append(log, l + "\n"))
            proc.stdout.close(); proc.wait()
            self._active_proc = None
            return proc.returncode == 0
        except Exception as e:
            self.after(0, lambda: self._log_append(log, f"[ERRO] {e}\n"))
            return False

    # ──────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────
    def _finish(self, phase_label, btn, start_time, success):
        elapsed_str = self._fmt_elapsed(time.time() - start_time)
        if success:
            self.after(0, lambda s=elapsed_str: phase_label.configure(
                text=f"✓ Concluído em {s}", text_color="#a3e635"))
        else:
            self.after(0, lambda s=elapsed_str: phase_label.configure(
                text=f"✗ Falhou após {s}", text_color="#f87171"))
        self.after(0, lambda: btn.configure(state="normal", text="Converter"))

    def _log_append(self, widget, text, clear=False):
        widget.configure(state="normal")
        if clear: widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.see("end")
        widget.configure(state="disabled")

    def _log_clear(self, widget):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _fmt_elapsed(self, seconds: float) -> str:
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h: return f"{h}h {m:02d}m {s:02d}s"
        if m: return f"{m}m {s:02d}s"
        return f"{s}s"

    def _on_close(self):
        if self._active_proc and self._active_proc.poll() is None:
            self._active_proc.terminate()
            try: self._active_proc.wait(timeout=3)
            except: self._active_proc.kill()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
