import customtkinter as ctk
import subprocess
import threading
import os
import re
import sys
import json
import time
import shutil
import struct
import string
import multiprocessing
from tkinter import filedialog
from PIL import Image

# ── Bundle paths ──────────────────────────────────────────
if getattr(sys, "frozen", False):
    _BUNDLE_DIR = sys._MEIPASS
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

_ICON_PATH      = os.path.join(_BUNDLE_DIR, "icon.ico")
_PS1_PATH       = os.path.join(_BUNDLE_DIR, "New-OsfExfatImage.ps1")
_OSFMOUNT_SETUP = os.path.join(_BUNDLE_DIR, "osfmount_setup.exe")
_MKPFS          = os.path.join(_BUNDLE_DIR, "mkpfs_cli.exe") if getattr(sys, "frozen", False) else "mkpfs"

_OSFMOUNT_CANDIDATES = [
    r"C:\Program Files\OSFMount\osfmount.com",
    r"C:\Program Files (x86)\OSFMount\osfmount.com",
    r"C:\Program Files\PassMark\OSFMount\osfmount.com",
    r"C:\Program Files (x86)\PassMark\OSFMount\osfmount.com",
]

def _find_osfmount() -> str | None:
    for p in _OSFMOUNT_CANDIDATES:
        if os.path.isfile(p): return p
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(folder, "osfmount.com")
        if os.path.isfile(candidate): return candidate
    return None

_RE_PROGRESS = re.compile(r"\[[#\-]+\]\s+(\d+)%\s+(\w+)")
_RE_PS1_STEP = re.compile(r"\[(\d+)/(\d+)\]")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VERSION = "1.2.0"

CONFIG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PFS Converter", "config.json")

def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def _save_config(data: dict):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)
    except: pass

# ── SFO / param.json parsers ──────────────────────────────
def _parse_sfo(path: str) -> dict:
    try:
        with open(path, "rb") as f: data = f.read()
        if data[:4] != b'\x00PSF': return {}
        _, key_tbl, data_tbl, n = struct.unpack_from('<IIII', data, 4)
        result = {}
        for i in range(n):
            off = 20 + i * 16
            key_off, fmt, dlen, _, doff = struct.unpack_from('<HHIII', data, off)
            key = data[key_tbl + key_off:].split(b'\x00')[0].decode('utf-8')
            raw = data[data_tbl + doff: data_tbl + doff + dlen]
            result[key] = struct.unpack_from('<I', raw)[0] if fmt == 0x0004 else raw.rstrip(b'\x00').decode('utf-8', errors='replace')
        return result
    except: return {}

def _parse_param_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f: data = json.load(f)
        title = "—"
        loc = data.get("localizedParameters", {})
        for lang in [loc.get("defaultLanguage", ""), "en-US", "pt-BR"] + list(loc.keys()):
            entry = loc.get(lang, {})
            if isinstance(entry, dict) and entry.get("titleName"):
                title = entry["titleName"]; break
        return {
            "TITLE":    title,
            "TITLE_ID": data.get("titleId", "—"),
            "APP_VER":  str(data.get("contentVersion", data.get("masterVersion", "—"))),
        }
    except: return {}

# ── Card style constants ───────────────────────────────────
_CARD_SEL  = {"border_color": "#0d9488", "fg_color": "#081c1a", "border_width": 2}
_CARD_NORM = {"border_color": "#2a2a3a", "fg_color": "#111120", "border_width": 1}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"PFS Converter v{VERSION}")
        self.geometry("1280x860")
        self.minsize(960, 680)
        self.resizable(True, True)
        if os.path.isfile(_ICON_PATH): self.iconbitmap(_ICON_PATH)

        self._cpu_count  = multiprocessing.cpu_count()
        self._active_proc = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        cfg = _load_config()
        self._saved_cpus = int(cfg.get("cpu_count", self._cpu_count))

        # Build state
        self._src_mode    = ctk.StringVar(value="folder")   # "folder" | "exfat"
        self._fmt_var     = ctk.StringVar(value=cfg.get("fmt", "pfs_raw"))
        self._comp_engine = ctk.StringVar(value=cfg.get("comp_engine", "zlib"))
        self._comp_level  = ctk.StringVar(value=cfg.get("comp_level", "9"))
        self._name_preset = ctk.StringVar(value=cfg.get("name_preset", "id_title_ver"))
        self._cpu_auto    = ctk.BooleanVar(value=False)
        self._src_folder  = ctk.StringVar()
        self._src_exfat   = ctk.StringVar()
        self._out_folder  = ctk.StringVar(value=cfg.get("out_folder", ""))
        self._temp_folder = ctk.StringVar(value=cfg.get("temp_folder", ""))
        self._output_name = ctk.StringVar()
        self._game_info   = {}
        self._adv_open    = False

        # Extrair state
        self._t5_source_file   = ctk.StringVar()
        self._t5_output_folder = ctk.StringVar(value=cfg.get("t5_output_dir", ""))
        self._t5_deep          = ctk.BooleanVar(value=True)
        self._t5_overwrite     = ctk.BooleanVar(value=True)

        self._build_ui()

        if not _find_osfmount():
            threading.Thread(target=self._auto_install_osfmount, daemon=True).start()

    # ────────────────────────────────────────────────────────
    #  Top-level UI
    # ────────────────────────────────────────────────────────
    def _build_ui(self):
        # Top bar
        topbar = ctk.CTkFrame(self, fg_color="#0a0a14", height=48, corner_radius=0)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        ctk.CTkLabel(topbar, text="🎮  PFS Converter",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=20)
        ctk.CTkLabel(topbar, text=f"v{VERSION}",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(side="left")

        self._nav_build  = ctk.CTkButton(topbar, text="Converter", width=120, height=32,
                                          fg_color="#0d9488", hover_color="#0a7b72",
                                          command=lambda: self._show_view("build"))
        self._nav_build.pack(side="left", padx=(24, 4))
        self._nav_extra  = ctk.CTkButton(topbar, text="Extrair", width=100, height=32,
                                          fg_color="#252535", hover_color="#353545",
                                          command=lambda: self._show_view("extra"))
        self._nav_extra.pack(side="left")

        # Build button — far right of topbar
        self._build_btn = ctk.CTkButton(topbar, text="▶  Build", width=130, height=32,
                                         fg_color="#0d9488", hover_color="#0a7b72",
                                         font=ctk.CTkFont(size=13, weight="bold"),
                                         command=self._build_start)
        self._build_btn.pack(side="right", padx=16)

        # Views
        self._view_build = ctk.CTkFrame(self, fg_color="transparent")
        self._view_extra = ctk.CTkFrame(self, fg_color="transparent")
        self._build_build_view(self._view_build)
        self._build_extra_view(self._view_extra)
        self._show_view("build")

    def _show_view(self, v: str):
        self._view_build.pack_forget()
        self._view_extra.pack_forget()
        if v == "build":
            self._view_build.pack(fill="both", expand=True)
            self._nav_build.configure(fg_color="#0d9488")
            self._nav_extra.configure(fg_color="#252535")
        else:
            self._view_extra.pack(fill="both", expand=True)
            self._nav_build.configure(fg_color="#252535")
            self._nav_extra.configure(fg_color="#0d9488")

    # ────────────────────────────────────────────────────────
    #  Build view  (sections 1-4, two columns)
    # ────────────────────────────────────────────────────────
    def _build_build_view(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)   # top row (sec1 + sec2) expands
        parent.rowconfigure(1, weight=0)   # bottom row (sec3) natural height

        # Top-left: sec1
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=(10, 5))

        # Top-right: format+output card
        right = ctk.CTkFrame(parent, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=(10, 5))

        # Bottom-left: sec3 (output folders)
        bot_left = ctk.CTkFrame(parent, fg_color="transparent")
        bot_left.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))

        # Bottom-right: sec4 (advanced, always visible)
        bot_right = ctk.CTkFrame(parent, fg_color="transparent")
        bot_right.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))

        self._build_sec1(left)
        self._build_right_card(right)
        self._build_sec3(bot_left)
        self._build_sec4(bot_right)
        self._refresh_sec3()

    # ── Section 1 — Source ─────────────────────────────────
    def _build_sec1(self, parent):
        card = self._card(parent)
        card.pack(fill="both", expand=True)

        self._sec_hdr(card, "1", "Source")

        # Mode toggle
        tog = ctk.CTkFrame(card, fg_color="transparent")
        tog.pack(fill="x", padx=16, pady=(0, 10))
        self._mode_btn_folder = ctk.CTkButton(tog, text="📁  Pasta do dump", width=160, height=28,
                                               fg_color="#0d9488", hover_color="#0a7b72",
                                               font=ctk.CTkFont(size=11),
                                               command=lambda: self._set_src_mode("folder"))
        self._mode_btn_folder.pack(side="left", padx=(0, 6))
        self._mode_btn_exfat = ctk.CTkButton(tog, text="💿  Arquivo .exfat", width=160, height=28,
                                              fg_color="#252535", hover_color="#353545",
                                              font=ctk.CTkFont(size=11),
                                              command=lambda: self._set_src_mode("exfat"))
        self._mode_btn_exfat.pack(side="left")

        # Art + text row (shown in folder mode)
        self._info_row_wrap = ctk.CTkFrame(card, fg_color="transparent")
        self._info_row_wrap.pack(fill="x", padx=16, pady=(0, 10))

        self._info_icon_lbl = ctk.CTkLabel(self._info_row_wrap, text="", width=84, height=84,
                                            corner_radius=8, fg_color="#1a1a2e")
        self._info_icon_lbl.pack(side="left", padx=(0, 14))

        txt = ctk.CTkFrame(self._info_row_wrap, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True)

        self._info_title_lbl = ctk.CTkLabel(txt, text="Selecione um dump",
                                             font=ctk.CTkFont(size=14, weight="bold"),
                                             anchor="w", justify="left")
        self._info_title_lbl.pack(fill="x")
        self._info_tid_lbl = ctk.CTkLabel(txt, text="",
                                           font=ctk.CTkFont(size=12), text_color="gray", anchor="w")
        self._info_tid_lbl.pack(fill="x", pady=(2, 8))

        stats = ctk.CTkFrame(txt, fg_color="transparent")
        stats.pack(fill="x")
        self._stat_ver  = self._stat_box(stats, "VERSION",     "—")
        self._stat_size = self._stat_box(stats, "DUMP SIZE",   "—")
        self._stat_free = self._stat_box(stats, "OUTPUT FREE", "—")

        # Status label
        self._src_status = ctk.CTkLabel(card, text="Selecione o dump abaixo",
                                         font=ctk.CTkFont(size=11), text_color="gray", anchor="w")
        self._src_status.pack(fill="x", padx=16, pady=(0, 6))

        # Folder picker
        self._src_folder_row = ctk.CTkFrame(card, fg_color="transparent")
        self._src_folder_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkEntry(self._src_folder_row, textvariable=self._src_folder,
                     placeholder_text="Pasta do dump...",
                     state="readonly").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(self._src_folder_row, text="Browse", width=90,
                      command=self._pick_src).pack(side="left")

        # exFAT file picker (hidden initially)
        self._src_exfat_row = ctk.CTkFrame(card, fg_color="transparent")
        ctk.CTkEntry(self._src_exfat_row, textvariable=self._src_exfat,
                     placeholder_text="Arquivo .exfat...",
                     state="readonly").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(self._src_exfat_row, text="Browse", width=90,
                      command=self._pick_src_exfat).pack(side="left")

    def _stat_box(self, parent, label, value):
        f = ctk.CTkFrame(parent, fg_color="#191928", corner_radius=6)
        f.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=9), text_color="#666688").pack(padx=10, pady=(5, 0))
        lbl = ctk.CTkLabel(f, text=value, font=ctk.CTkFont(size=12, weight="bold"))
        lbl.pack(padx=10, pady=(0, 5))
        return lbl

    # ── Right card — Format + Output name + Progress ──────
    def _build_right_card(self, parent):
        card = self._card(parent)
        card.pack(fill="both", expand=True, pady=(0, 8))

        # ── Format ──────────────────────────────────────────
        self._sec_hdr(card, "2", "Format & Output")
        self._sec2_subtitle = ctk.CTkLabel(card, text="Selecione o formato de saída",
                     font=ctk.CTkFont(size=11), text_color="gray", anchor="w")
        self._sec2_subtitle.pack(fill="x", padx=24, pady=(0, 10))

        # Normal 3-card row (folder mode)
        self._cards_normal_row = ctk.CTkFrame(card, fg_color="transparent")
        self._cards_normal_row.pack(fill="x", padx=16, pady=(0, 12))
        self._cards_normal_row.columnconfigure((0, 1, 2), weight=1, uniform="fc")

        self._fmt_cards = {}
        formats = [
            ("exfat",     "💾", "exFAT",    "Imagem montável\npara a maioria",  True),
            ("pfs_raw",   "📦", "PFS Raw",  ".dat → .ffpfsc\ncomprimido",       False),
            ("pfs_exfat", "🗜️", "PFS exFAT","Via exFAT → .ffpfsc\ncomprimido", False),
        ]
        for col, (key, icon, name, desc, rec) in enumerate(formats):
            sel = self._fmt_var.get() == key
            fc = ctk.CTkFrame(self._cards_normal_row, corner_radius=8, **(_CARD_SEL if sel else _CARD_NORM))
            fc.grid(row=0, column=col, padx=5, sticky="nsew")
            top = ctk.CTkFrame(fc, fg_color="transparent")
            top.pack(fill="x", padx=8, pady=(8, 0))
            ctk.CTkLabel(top, text=icon, font=ctk.CTkFont(size=16)).pack(side="left")
            chk = ctk.CTkLabel(top, text="✓" if sel else "",
                               font=ctk.CTkFont(size=12), text_color="#0d9488")
            chk.pack(side="right")
            ctk.CTkLabel(fc, text=name, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", padx=8, pady=(2, 0))
            ctk.CTkLabel(fc, text=desc, font=ctk.CTkFont(size=9), text_color="gray",
                         anchor="w", justify="left").pack(fill="x", padx=8, pady=(1, 0))
            if rec:
                ctk.CTkLabel(fc, text=" RECOMENDADO ", font=ctk.CTkFont(size=8, weight="bold"),
                              fg_color="#0d9488", corner_radius=4, text_color="white"
                              ).pack(anchor="w", padx=8, pady=(4, 0))
            ctk.CTkFrame(fc, fg_color="transparent", height=8).pack()
            self._bind_card_click(fc, key)
            self._fmt_cards[key] = (fc, chk)

        # Single PFS card (exfat file mode) — hidden initially
        self._cards_exfat_row = ctk.CTkFrame(card, fg_color="transparent")
        self._cards_exfat_row.columnconfigure(0, weight=1)
        fc_pfs = ctk.CTkFrame(self._cards_exfat_row, corner_radius=8, **_CARD_SEL)
        fc_pfs.grid(row=0, column=0, padx=5, sticky="new", pady=(0, 8))
        top_pfs = ctk.CTkFrame(fc_pfs, fg_color="transparent")
        top_pfs.pack(fill="x", padx=8, pady=(8, 0))
        ctk.CTkLabel(top_pfs, text="🗜️", font=ctk.CTkFont(size=16)).pack(side="left")
        ctk.CTkLabel(top_pfs, text="✓", font=ctk.CTkFont(size=12), text_color="#0d9488").pack(side="right")
        ctk.CTkLabel(fc_pfs, text="PFS", font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", padx=8, pady=(2, 0))
        ctk.CTkLabel(fc_pfs, text=".exfat → .ffpfsc comprimido", font=ctk.CTkFont(size=9),
                     text_color="gray", anchor="w").pack(fill="x", padx=8, pady=(1, 8))

        # ── Divider ─────────────────────────────────────────
        ctk.CTkFrame(card, fg_color="#252535", height=1).pack(fill="x", padx=16, pady=(0, 12))

        # ── Output name ─────────────────────────────────────
        ctk.CTkLabel(card, text="OUTPUT NAME PRESET",
                     font=ctk.CTkFont(size=10, weight="bold"), text_color="gray", anchor="w").pack(fill="x", padx=16, pady=(0, 6))
        pf = ctk.CTkFrame(card, fg_color="transparent")
        pf.pack(fill="x", padx=16, pady=(0, 8))
        for val, lbl in [("id", "Title ID"), ("id_title", "+ Título"),
                         ("id_title_ver", "+ Versão"), ("custom", "Personalizado")]:
            ctk.CTkRadioButton(pf, text=lbl, variable=self._name_preset, value=val,
                               radiobutton_width=14, radiobutton_height=14,
                               command=self._update_out_name).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(card, text="Output name", font=ctk.CTkFont(size=11),
                     text_color="gray", anchor="w").pack(fill="x", padx=16)
        ctk.CTkEntry(card, textvariable=self._output_name,
                     placeholder_text="nome_do_arquivo.ffpfsc").pack(fill="x", padx=16, pady=(4, 12))

        # ── Divider ─────────────────────────────────────────
        ctk.CTkFrame(card, fg_color="#252535", height=1).pack(fill="x", padx=16, pady=(0, 10))

        # ── Progress ─────────────────────────────────────────
        prow = ctk.CTkFrame(card, fg_color="transparent")
        prow.pack(fill="x", padx=16, pady=(0, 6))
        self._build_phase = ctk.CTkLabel(prow, text="Pronto", anchor="w", font=ctk.CTkFont(size=12))
        self._build_phase.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(prow, text="📋 Log", width=76, height=26,
                      fg_color="#252535", hover_color="#353545",
                      font=ctk.CTkFont(size=11),
                      command=self._open_log_window).pack(side="right")

        self._build_bar = ctk.CTkProgressBar(card, height=12)
        self._build_bar.set(0)
        self._build_bar.pack(fill="x", padx=16, pady=(0, 16))

        # Hidden log textbox (shown in popup)
        self._build_log = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Courier New", size=11),
                                          state="disabled", width=1, height=1)
        self._log_window = None
        self._log_view   = None

    # ── Section 3 — Configure output ───────────────────────
    def _build_sec3(self, parent):
        card = self._card(parent)
        card.pack(fill="both", expand=True)

        self._sec_hdr(card, "3", "Configure output")

        ctk.CTkLabel(card, text="Output folder", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=16)
        ctk.CTkLabel(card, text="onde a imagem será gravada",
                     font=ctk.CTkFont(size=10), text_color="gray", anchor="w").pack(fill="x", padx=16)
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(4, 12))
        ctk.CTkEntry(r1, textvariable=self._out_folder,
                     placeholder_text="Pasta de saída...").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r1, text="Browse", width=90, command=self._pick_out).pack(side="left")

        self._temp_wrap = ctk.CTkFrame(card, fg_color="transparent")
        ctk.CTkLabel(self._temp_wrap, text="Temp folder", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(self._temp_wrap, text="redirect do build spool — PFS Raw e PFS exFAT",
                     font=ctk.CTkFont(size=10), text_color="gray", anchor="w").pack(fill="x")
        r2 = ctk.CTkFrame(self._temp_wrap, fg_color="transparent")
        r2.pack(fill="x", pady=(4, 0))
        ctk.CTkEntry(r2, textvariable=self._temp_folder,
                     placeholder_text="Pasta temporária...").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r2, text="Browse", width=90, command=self._pick_temp).pack(side="left")

    # ── Section 4 — Advanced options (always visible) ──────
    def _build_sec4(self, parent):
        card = self._card(parent)
        card.pack(fill="both", expand=True)

        self._sec_hdr(card, "4", "Advanced Options")

        # CPU
        ctk.CTkLabel(card, text="CPU threads", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=16)
        ctk.CTkLabel(card, text="paralelo durante criação da imagem",
                     font=ctk.CTkFont(size=10), text_color="gray", anchor="w").pack(fill="x", padx=16)
        cpu_row = ctk.CTkFrame(card, fg_color="transparent")
        cpu_row.pack(fill="x", padx=16, pady=(6, 12))
        self._cpu_lbl = ctk.CTkLabel(cpu_row, text=str(self._saved_cpus), width=36)
        self._cpu_lbl.pack(side="right")
        ctk.CTkCheckBox(cpu_row, text="Auto", variable=self._cpu_auto,
                        command=self._on_cpu_auto_toggle, width=70).pack(side="right", padx=(0, 8))
        self._cpu_slider = ctk.CTkSlider(cpu_row, from_=1, to=self._cpu_count,
                                          number_of_steps=self._cpu_count - 1,
                                          command=self._on_cpu_slider)
        self._cpu_slider.set(self._saved_cpus)
        self._cpu_slider.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Compression (shown conditionally)
        self._comp_wrap = ctk.CTkFrame(card, fg_color="transparent")

        ctk.CTkLabel(self._comp_wrap, text="Compression engine",
                     font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=16)
        for val, lbl in [("zlib", "zlib — safe (padrão)"), ("zlib-isa", "zlib-isa — experimental")]:
            ctk.CTkRadioButton(self._comp_wrap, text=lbl, variable=self._comp_engine,
                               value=val, radiobutton_width=16, radiobutton_height=16
                               ).pack(anchor="w", padx=28, pady=2)

        ctk.CTkLabel(self._comp_wrap, text="Compression level",
                     font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=16, pady=(10, 4))
        _lvl_map = {"1": "1 — Mínima", "3": "3 — Média", "6": "6 — Alta", "9": "9 — Máxima"}
        self._comp_menu = ctk.CTkOptionMenu(
            self._comp_wrap,
            values=list(_lvl_map.values()),
            command=lambda v: self._comp_level.set(v[0])
        )
        self._comp_menu.set(_lvl_map.get(self._comp_level.get(), "9 — Máxima"))
        self._comp_menu.pack(fill="x", padx=16, pady=(0, 12))

    def _refresh_sec3(self):
        fmt = self._fmt_var.get()
        mode = self._src_mode.get()
        needs_temp = (mode == "folder") and (fmt in ("pfs_raw", "pfs_exfat"))
        needs_comp = (mode == "exfat") or (fmt in ("pfs_raw", "pfs_exfat"))
        if needs_temp:
            self._temp_wrap.pack(fill="x", padx=16, pady=(0, 12))
        else:
            self._temp_wrap.pack_forget()
        if needs_comp:
            self._comp_wrap.pack(fill="x")
        else:
            self._comp_wrap.pack_forget()


    def _open_log_window(self):
        if self._log_window and self._log_window.winfo_exists():
            self._log_window.lift(); self._log_window.focus(); return
        win = ctk.CTkToplevel(self)
        win.title("Log de conversão")
        win.resizable(True, True)
        self._log_window = win

        # Position log window to the right of the main window
        self.update_idletasks()
        mx = self.winfo_x()
        my = self.winfo_y()
        mw = self.winfo_width()
        mh = self.winfo_height()
        log_w = 600
        win.geometry(f"{log_w}x{mh}+{mx + mw}+{my}")

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(bar, text="Log de conversão", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(bar, text="Limpar", width=70, height=26,
                      fg_color="#252535", hover_color="#353545",
                      command=self._clear_both_logs).pack(side="right")

        self._log_view = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Courier New", size=11),
                                         state="normal")
        self._log_view.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Copy current log content into the view
        content = self._build_log.get("1.0", "end")
        self._log_view.insert("1.0", content)
        self._log_view.see("end")
        self._log_view.configure(state="disabled")

        def _on_close():
            self._log_view = None
            self._log_window = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

    def _clear_both_logs(self):
        self._log_clear(self._build_log)
        if self._log_view and self._log_window and self._log_window.winfo_exists():
            self._log_view.configure(state="normal")
            self._log_view.delete("1.0", "end")
            self._log_view.configure(state="disabled")

    # ── Extrair view ───────────────────────────────────────
    def _build_extra_view(self, parent):
        card = self._card(parent)
        card.pack(fill="both", expand=True, padx=10, pady=10)
        self._sec_hdr(card, "↓", "Extrair arquivos de imagem PFS")
        ctk.CTkLabel(card, text="Extração a partir de .ffpfsc, .ffpfs ou .exfat",
                     font=ctk.CTkFont(size=11), text_color="gray", anchor="w").pack(fill="x", padx=24, pady=(0, 12))

        ctk.CTkLabel(card, text="Arquivo de origem", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=16)
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(4, 10))
        ctk.CTkEntry(r1, textvariable=self._t5_source_file,
                     placeholder_text="Arquivo de imagem...").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r1, text="Browse", width=90, command=self._t5_pick_src).pack(side="left")

        ctk.CTkLabel(card, text="Pasta de saída", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=16)
        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(4, 10))
        ctk.CTkEntry(r2, textvariable=self._t5_output_folder,
                     placeholder_text="Onde extrair...").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(r2, text="Browse", width=90, command=self._t5_pick_out).pack(side="left")

        opt = ctk.CTkFrame(card, fg_color="transparent")
        opt.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkCheckBox(opt, text="Extrair arquivos internos (--deep)", variable=self._t5_deep).pack(side="left", padx=(0, 24))
        ctk.CTkCheckBox(opt, text="Sobrescrever existentes (--overwrite)", variable=self._t5_overwrite).pack(side="left")

        self._t5_btn = ctk.CTkButton(card, text="Extrair", height=44,
                                      fg_color="#0d9488", hover_color="#0a7b72",
                                      font=ctk.CTkFont(size=14, weight="bold"), command=self._t5_start)
        self._t5_btn.pack(fill="x", padx=16, pady=(4, 10))

        self._t5_phase = ctk.CTkLabel(card, text="", anchor="w", font=ctk.CTkFont(size=12))
        self._t5_phase.pack(fill="x", padx=16, pady=(4, 2))
        self._t5_bar = ctk.CTkProgressBar(card, height=14, mode="indeterminate")
        self._t5_bar.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(card, text="Log", anchor="w", text_color="gray",
                     font=ctk.CTkFont(size=11)).pack(fill="x", padx=16)
        self._t5_log = ctk.CTkTextbox(card, font=ctk.CTkFont(family="Courier New", size=11), state="disabled")
        self._t5_log.pack(fill="both", expand=True, padx=16, pady=(4, 16))

    # ────────────────────────────────────────────────────────
    #  UI helpers
    # ────────────────────────────────────────────────────────
    def _bind_card_click(self, widget, key: str):
        """Recursively bind left-click on every child of a format card."""
        widget.bind("<Button-1>", lambda e, k=key: self._select_fmt(k))
        for child in widget.winfo_children():
            self._bind_card_click(child, key)

    def _card(self, parent):
        return ctk.CTkFrame(parent, corner_radius=10, fg_color="#111120",
                            border_width=1, border_color="#252535")

    def _sec_hdr(self, parent, n, title):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=16, pady=(14, 10))
        ctk.CTkLabel(f, text=str(n), width=24, height=24, corner_radius=12,
                     fg_color="#1d3557", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(side="left")

    # ────────────────────────────────────────────────────────
    #  Format selection
    # ────────────────────────────────────────────────────────
    def _select_fmt(self, key: str):
        self._fmt_var.set(key)
        for k, (fc, chk) in self._fmt_cards.items():
            sel = k == key
            fc.configure(**(_CARD_SEL if sel else _CARD_NORM))
            chk.configure(text="✓" if sel else "")
        self._refresh_sec3()
        self._update_out_name()
        _save_config({**_load_config(), "fmt": key})

    # ────────────────────────────────────────────────────────
    #  Source mode toggle
    # ────────────────────────────────────────────────────────
    def _set_src_mode(self, mode: str):
        self._src_mode.set(mode)
        if mode == "folder":
            self._mode_btn_folder.configure(fg_color="#0d9488")
            self._mode_btn_exfat.configure(fg_color="#252535")
            self._src_exfat_row.pack_forget()
            self._src_folder_row.pack(fill="x", padx=16, pady=(0, 14))
            self._cards_normal_row.pack(fill="x", padx=16, pady=(0, 16))
            self._cards_exfat_row.pack_forget()
            self._sec2_subtitle.configure(text="Selecione o formato e configure as opções abaixo")
        else:
            self._mode_btn_exfat.configure(fg_color="#0d9488")
            self._mode_btn_folder.configure(fg_color="#252535")
            self._src_folder_row.pack_forget()
            self._src_exfat_row.pack(fill="x", padx=16, pady=(0, 14))
            self._cards_normal_row.pack_forget()
            self._cards_exfat_row.pack(fill="x", padx=16)
            self._sec2_subtitle.configure(text="Formato fixo: .exfat → .ffpfsc comprimido")
            self._info_title_lbl.configure(text="Selecione um arquivo .exfat")
            self._info_tid_lbl.configure(text="")
            self._stat_ver.configure(text="—")
            self._stat_size.configure(text="—")
            self._info_icon_lbl.configure(image=None, text="")
            self._src_status.configure(text="Selecione o arquivo .exfat abaixo", text_color="gray")
        self._refresh_sec3()
        self._update_out_name()

    # ────────────────────────────────────────────────────────
    #  Pickers
    # ────────────────────────────────────────────────────────
    def _pick_src(self):
        path = filedialog.askdirectory(title="Selecione o dump")
        if path:
            self._src_folder.set(path)
            self._update_out_name()
            self._update_free_space()
            threading.Thread(target=self._load_info, args=(path,), daemon=True).start()

    def _pick_src_exfat(self):
        path = filedialog.askopenfilename(
            title="Selecione o arquivo .exfat",
            filetypes=[("Imagem exFAT", "*.exfat"), ("All files", "*.*")],
        )
        if path:
            self._src_exfat.set(path)
            self._game_info = {}
            self._update_out_name()
            self._src_status.configure(text="Lendo metadados...", text_color="gray")
            threading.Thread(target=self._load_info_from_exfat, args=(path,), daemon=True).start()

    def _load_info_from_exfat(self, exfat_path: str):
        osf = _find_osfmount()
        if not osf:
            self.after(0, lambda: self._src_status.configure(
                text="OSFMount não encontrado — sem prévia", text_color="#f87171"))
            return
        drive = self._find_free_drive()
        if not drive:
            self.after(0, lambda: self._src_status.configure(
                text="Nenhuma letra de drive disponível", text_color="#f87171"))
            return
        try:
            r = subprocess.run(
                [osf, "-a", "-t", "file", "-f", exfat_path, "-o", "ro,rem", "-m", drive],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
            if r.returncode != 0:
                err = (r.stdout + r.stderr).strip().splitlines()
                msg = err[-1] if err else f"código {r.returncode}"
                self.after(0, lambda m=msg: self._src_status.configure(
                    text=f"Falha ao montar: {m}", text_color="#f87171"))
                return
            mount_root = drive + "\\"
            self._load_info(mount_root)
        except Exception as e:
            self.after(0, lambda: self._src_status.configure(
                text=f"Erro: {e}", text_color="#f87171"))
        finally:
            try:
                subprocess.run([osf, "-d", "-m", drive],
                               capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            except: pass

    def _pick_out(self):
        path = filedialog.askdirectory(title="Pasta de saída")
        if path:
            self._out_folder.set(path)
            self._update_free_space()
            _save_config({**_load_config(), "out_folder": path})

    def _pick_temp(self):
        path = filedialog.askdirectory(title="Pasta temporária")
        if path:
            self._temp_folder.set(path)
            _save_config({**_load_config(), "temp_folder": path})

    def _update_free_space(self):
        out = self._out_folder.get()
        if out and os.path.isdir(out):
            try:
                free = shutil.disk_usage(out).free
                txt = f"{free/(1<<30):.1f} GB" if free >= 1<<30 else f"{free/(1<<20):.0f} MB"
                self._stat_free.configure(text=txt)
            except: pass

    # ────────────────────────────────────────────────────────
    #  Output name generation
    # ────────────────────────────────────────────────────────
    def _update_out_name(self, *_):
        if self._name_preset.get() == "custom": return
        info  = self._game_info
        tid   = re.sub(r'[\\/:*?"<>|]', '', info.get("title_id", "")).strip()
        title = re.sub(r'[\\/:*?"<>|]', '', info.get("titulo",   "")).strip()
        ver   = re.sub(r'[\\/:*?"<>|]', '', info.get("versao",   "")).strip()
        ext   = ".exfat" if (self._src_mode.get() == "folder" and self._fmt_var.get() == "exfat") else ".ffpfsc"
        base  = tid or "output"
        p = self._name_preset.get()
        sep = f"{base} - " if title else base
        if p == "id":           name = f"{base}{ext}"
        elif p == "id_title":   name = f"{sep}{title}{ext}" if title else f"{base}{ext}"
        else:                   name = f"{sep}{title} ({ver}){ext}" if title and ver else (f"{sep}{title}{ext}" if title else f"{base}{ext}")
        self._output_name.set(name)

    # ────────────────────────────────────────────────────────
    #  CPU slider
    # ────────────────────────────────────────────────────────
    def _on_cpu_slider(self, value):
        cpus = int(value)
        self._cpu_lbl.configure(text=str(cpus))
        _save_config({**_load_config(), "cpu_count": cpus})

    def _on_cpu_auto_toggle(self):
        auto = self._cpu_auto.get()
        self._cpu_slider.configure(state="disabled" if auto else "normal")
        self._cpu_lbl.configure(text="Auto" if auto else str(int(self._cpu_slider.get())))

    def _get_cpus(self):
        return 0 if self._cpu_auto.get() else int(self._cpu_slider.get())

    # ────────────────────────────────────────────────────────
    #  Build
    # ────────────────────────────────────────────────────────
    def _build_start(self):
        mode     = self._src_mode.get()
        out_dir  = self._out_folder.get().strip()
        out_name = self._output_name.get().strip()
        fmt      = self._fmt_var.get()
        cpus     = self._get_cpus()
        comp_lvl = self._comp_level.get().split()[0]
        comp_eng = self._comp_engine.get()
        temp_dir = self._temp_folder.get().strip() or os.environ.get("TEMP", os.path.expanduser("~"))

        if not out_dir:
            self._log_append(self._build_log, "[ERRO] Informe a pasta de saída.\n", clear=True); return
        if not out_name:
            self._log_append(self._build_log, "[ERRO] Informe o nome do arquivo de saída.\n", clear=True); return

        self._build_btn.configure(state="disabled", text="Convertendo...")
        self._build_bar.set(0)
        self._build_phase.configure(text="")
        self._log_clear(self._build_log)
        self._build_start_time = time.time()
        output = os.path.join(out_dir, out_name)

        if mode == "exfat":
            src_exfat = self._src_exfat.get().strip()
            if not src_exfat or not os.path.isfile(src_exfat):
                self._log_append(self._build_log, "[ERRO] Selecione um arquivo .exfat válido.\n", clear=True)
                self._build_btn.configure(state="normal", text="▶  Build"); return
            threading.Thread(target=self._do_build_from_exfat,
                             args=(src_exfat, output, cpus, comp_eng, comp_lvl),
                             daemon=True).start()
        else:
            folder = self._src_folder.get().strip()
            if not folder or not os.path.isdir(folder):
                self._log_append(self._build_log, "[ERRO] Selecione um dump válido.\n", clear=True)
                self._build_btn.configure(state="normal", text="▶  Build"); return
            if fmt == "pfs_exfat" and not _find_osfmount():
                self._log_append(self._build_log, "[ERRO] OSFMount não encontrado (necessário para PFS exFAT).\n", clear=True)
                self._build_btn.configure(state="normal", text="▶  Build"); return
            threading.Thread(target=self._do_build,
                             args=(folder, output, temp_dir, cpus, fmt, comp_eng, comp_lvl),
                             daemon=True).start()

    def _do_build(self, folder, output, temp_dir, cpus, fmt, comp_eng, comp_lvl):
        name = os.path.basename(folder.rstrip("/\\"))
        staging = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "_mkpfs_staging")
        os.makedirs(staging, exist_ok=True)

        def pack_file_cmd(src, dst):
            cmd = [_MKPFS, "pack", "file", "--version", "PS5", "--inode-bits", "32",
                   "--cpu-count", str(cpus), "--temp-folder", staging]
            if comp_eng == "zlib-isa":
                cmd += ["--compression-backend", "zlib-isa"]
            if comp_lvl.isdigit():
                cmd += ["--compression-level", comp_lvl]
            cmd += [src, dst]
            return cmd

        success = False
        try:
            if fmt == "exfat":
                if os.path.exists(output): os.remove(output)
                cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                       "-File", _PS1_PATH, "-ImagePath", output, "-SourceDir", folder, "-ForceOverwrite"]
                success = self._run_cmd_ps1(cmd, self._build_bar, self._build_phase, self._build_log)

            elif fmt == "pfs_raw":
                dat = os.path.join(temp_dir, "pfs_image.dat")
                if os.path.exists(dat): os.remove(dat)
                if os.path.exists(output): os.remove(output)
                cmd1 = [_MKPFS, "pack", "folder", "--raw", "--no-compress",
                        "--no-adjust-output-file-extension", "--version", "PS5",
                        "--inode-bits", "32", "--cpu-count", str(cpus), folder, dat]
                success = self._run_cmd(cmd1, self._build_bar, self._build_phase,
                                         self._build_log, "Passo 1/2", success_file=dat)
                if success:
                    success = self._run_cmd(pack_file_cmd(dat, output),
                                             self._build_bar, self._build_phase,
                                             self._build_log, "Passo 2/2", success_file=output)
                if os.path.exists(dat):
                    try: os.remove(dat)
                    except: pass

            elif fmt == "pfs_exfat":
                os.makedirs(temp_dir, exist_ok=True)
                exfat = os.path.join(temp_dir, f"{name}.exfat")
                self.after(0, lambda: self._build_phase.configure(
                    text="Passo 1/2 — Criando imagem exFAT...", text_color="white"))
                cmd_ps1 = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-File", _PS1_PATH, "-ImagePath", exfat,
                           "-SourceDir", folder, "-ForceOverwrite"]
                success = self._run_cmd_ps1(cmd_ps1, self._build_bar, self._build_phase,
                                             self._build_log, step_offset=0, total_steps=2)
                if success:
                    if os.path.exists(output): os.remove(output)
                    success = self._run_cmd(pack_file_cmd(exfat, output),
                                             self._build_bar, self._build_phase,
                                             self._build_log, "Passo 2/2", success_file=output)
                if os.path.exists(exfat):
                    try: os.remove(exfat)
                    except: pass
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        self._finish(self._build_phase, self._build_btn, self._build_start_time, success, "▶  Build")

    def _do_build_from_exfat(self, src_exfat, output, cpus, comp_eng, comp_lvl):
        staging = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "_mkpfs_staging")
        os.makedirs(staging, exist_ok=True)
        try:
            if os.path.exists(output): os.remove(output)
            cmd = [_MKPFS, "pack", "file", "--version", "PS5", "--inode-bits", "32",
                   "--cpu-count", str(cpus), "--temp-folder", staging]
            if comp_eng == "zlib-isa":
                cmd += ["--compression-backend", "zlib-isa"]
            if comp_lvl.isdigit():
                cmd += ["--compression-level", comp_lvl]
            cmd += [src_exfat, output]
            success = self._run_cmd(cmd, self._build_bar, self._build_phase,
                                     self._build_log, "", success_file=output)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        self._finish(self._build_phase, self._build_btn, self._build_start_time, success, "▶  Build")

    # ────────────────────────────────────────────────────────
    #  Extrair
    # ────────────────────────────────────────────────────────
    def _t5_pick_src(self):
        current = self._t5_source_file.get()
        path = filedialog.askopenfilename(
            title="Selecione o arquivo de imagem",
            filetypes=[("Imagens PFS", "*.ffpfsc *.ffpfs *.exfat"), ("All files", "*.*")],
            initialdir=os.path.dirname(current) if current else None,
        )
        if path:
            self._t5_source_file.set(path)
            base = os.path.splitext(os.path.basename(path))[0]
            out_dir = os.path.dirname(self._t5_output_folder.get()) if self._t5_output_folder.get() else os.path.dirname(path)
            self._t5_output_folder.set(os.path.join(out_dir, base))
            _save_config({**_load_config(), "t5_output_dir": os.path.dirname(path)})

    def _t5_pick_out(self):
        current = self._t5_output_folder.get()
        path = filedialog.askdirectory(title="Pasta de saída", initialdir=current if current else None)
        if path:
            self._t5_output_folder.set(path)
            _save_config({**_load_config(), "t5_output_dir": path})

    def _t5_start(self):
        source = self._t5_source_file.get().strip()
        output = self._t5_output_folder.get().strip()
        if not source or not os.path.isfile(source):
            self._log_append(self._t5_log, "[ERRO] Selecione um arquivo de imagem válido.\n", clear=True); return
        if not output:
            self._log_append(self._t5_log, "[ERRO] Informe a pasta de saída.\n", clear=True); return
        self._t5_btn.configure(state="disabled", text="Extraindo...")
        self._t5_bar.start()
        self._t5_phase.configure(text="Extraindo arquivos...", text_color="white")
        self._log_clear(self._t5_log)
        self._t5_start_time = time.time()
        threading.Thread(target=self._t5_run, args=(source, output), daemon=True).start()

    def _t5_run(self, source, output):
        cmd = [_MKPFS, "unpack", "--no-progress"]
        if self._t5_overwrite.get(): cmd.append("--overwrite")
        if self._t5_deep.get():     cmd.append("--deep")
        cmd += [source, output]
        try:
            env = os.environ.copy(); env["PYTHONUTF8"] = "1"; env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=subprocess.CREATE_NO_WINDOW, env=env)
            self._active_proc = proc
            for line in proc.stdout:
                s = line.rstrip("\n")
                if s: self.after(0, lambda l=s: self._log_append(self._t5_log, l + "\n"))
            proc.stdout.close(); proc.wait()
            self._active_proc = None
            success = proc.returncode == 0
        except FileNotFoundError:
            self.after(0, lambda: self._log_append(self._t5_log, f"[ERRO] mkpfs não encontrado: {_MKPFS}\n"))
            success = False
        except Exception as e:
            self.after(0, lambda: self._log_append(self._t5_log, f"[ERRO] {e}\n"))
            success = False
        self.after(0, self._t5_bar.stop)
        self._finish(self._t5_phase, self._t5_btn, self._t5_start_time, success, "Extrair")

    # ────────────────────────────────────────────────────────
    #  Game info loading
    # ────────────────────────────────────────────────────────
    def _load_info(self, folder: str):
        sce_sys   = os.path.join(folder, "sce_sys")
        json_path = os.path.join(sce_sys, "param.json")
        sfo_path  = os.path.join(sce_sys, "param.sfo")
        icon_path = os.path.join(sce_sys, "icon0.png")

        icon_img = None
        if os.path.isfile(icon_path):
            try:
                icon_img = Image.open(icon_path).convert("RGBA").resize((84, 84), Image.LANCZOS)
            except: pass

        raw = {}
        if os.path.isfile(json_path):   raw = _parse_param_json(json_path)
        elif os.path.isfile(sfo_path):  raw = _parse_sfo(sfo_path)

        try:
            total = 0
            for dp, _, fns in os.walk(folder):
                for f in fns:
                    try: total += os.path.getsize(os.path.join(dp, f))
                    except OSError: pass
            size_str = f"{total/(1<<30):.2f} GB" if total >= 1<<30 else f"{total/(1<<20):.2f} MB"
        except: size_str = "—"

        title    = str(raw.get("TITLE") or raw.get("TITLE_00") or "") if raw else ""
        title_id = str(raw.get("TITLE_ID", "")) if raw else ""
        versao   = str(raw.get("APP_VER", "")) if raw else ""

        self._game_info = {"titulo": title, "title_id": title_id, "versao": versao, "tamanho": size_str}

        def update():
            if icon_img:
                ctk_img = ctk.CTkImage(light_image=icon_img, dark_image=icon_img, size=(84, 84))
                self._info_icon_lbl.configure(image=ctk_img, text="")
                self._info_icon_lbl._ctk_image = ctk_img
            self._info_title_lbl.configure(text=title or os.path.basename(folder.rstrip("/\\")))
            self._info_tid_lbl.configure(text=title_id)
            self._stat_ver.configure(text=versao or "—")
            self._stat_size.configure(text=size_str)
            self._src_status.configure(text="✓ Pronto para converter", text_color="#0d9488")
            self._update_out_name()

        self.after(0, update)

    # ────────────────────────────────────────────────────────
    #  Core runners
    # ────────────────────────────────────────────────────────
    def _run_cmd(self, cmd, bar, phase_label, log, step_prefix, success_file=None) -> bool:
        try:
            env = os.environ.copy(); env["PYTHONUTF8"] = "1"; env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=subprocess.CREATE_NO_WINDOW, env=env)
            self._active_proc = proc
            for line in proc.stdout:
                m = _RE_PROGRESS.search(line)
                if m:
                    pct = int(m.group(1)) / 100.0
                    phase = m.group(2).capitalize()
                    txt = f"{step_prefix} — {phase}  {int(pct*100)}%" if step_prefix else f"{phase}  {int(pct*100)}%"
                    self.after(0, lambda v=pct, t=txt: (bar.set(v), phase_label.configure(text=t, text_color="white")))
                else:
                    s = line.rstrip("\n")
                    if s: self.after(0, lambda l=s: self._log_append(log, l + "\n"))
            proc.stdout.close(); proc.wait()
            self._active_proc = None
            file_ok = bool(success_file and os.path.exists(success_file) and os.path.getsize(success_file) > 0)
            return proc.returncode == 0 or file_ok
        except FileNotFoundError:
            self.after(0, lambda: self._log_append(log, f"[ERRO] mkpfs não encontrado: {_MKPFS}\n"))
            return False
        except Exception as e:
            self.after(0, lambda: self._log_append(log, f"[ERRO] {e}\n"))
            return False

    def _run_cmd_ps1(self, cmd, bar, phase_label, log, step_offset=0, total_steps=1) -> bool:
        step_labels = {1: "Criando e montando imagem...", 2: "Formatando exFAT...",
                       3: "Copiando arquivos...", 4: "Desmontando volume..."}
        try:
            env = os.environ.copy(); env["PYTHONUTF8"] = "1"; env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=subprocess.CREATE_NO_WINDOW, env=env)
            self._active_proc = proc
            for line in proc.stdout:
                s = line.rstrip("\n")
                if not s: continue
                m = _RE_PS1_STEP.search(s)
                if m:
                    step = int(m.group(1)); total = int(m.group(2))
                    pct = (step_offset + step / total) / total_steps
                    lbl = step_labels.get(step, s)
                    if total_steps > 1: lbl = f"Passo 1/2 — {lbl}"
                    self.after(0, lambda v=pct, t=lbl: (bar.set(v), phase_label.configure(text=t, text_color="white")))
                self.after(0, lambda l=s: self._log_append(log, l + "\n"))
            proc.stdout.close(); proc.wait()
            self._active_proc = None
            return proc.returncode == 0
        except Exception as e:
            self.after(0, lambda: self._log_append(log, f"[ERRO] {e}\n"))
            return False

    # ────────────────────────────────────────────────────────
    #  Helpers
    # ────────────────────────────────────────────────────────
    def _finish(self, phase_label, btn, start_time, success, btn_label="Converter"):
        elapsed = self._fmt_elapsed(time.time() - start_time)
        text  = f"✓ Concluído em {elapsed}" if success else f"✗ Falhou após {elapsed}"
        color = "#a3e635" if success else "#f87171"
        self.after(0, lambda: phase_label.configure(text=text, text_color=color))
        self.after(0, lambda: btn.configure(state="normal", text=btn_label))

    def _log_append(self, widget, text, clear=False):
        widget.configure(state="normal")
        if clear: widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.see("end")
        widget.configure(state="disabled")
        # Mirror to popup view if open
        if widget is self._build_log and self._log_view and self._log_window and self._log_window.winfo_exists():
            self._log_view.configure(state="normal")
            if clear: self._log_view.delete("1.0", "end")
            self._log_view.insert("end", text)
            self._log_view.see("end")
            self._log_view.configure(state="disabled")

    def _log_clear(self, widget):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _fmt_elapsed(self, seconds: float) -> str:
        s = int(seconds)
        h, r = divmod(s, 3600); m, s = divmod(r, 60)
        if h: return f"{h}h {m:02d}m {s:02d}s"
        if m: return f"{m}m {s:02d}s"
        return f"{s}s"

    def _on_close(self):
        if self._active_proc and self._active_proc.poll() is None:
            self._active_proc.terminate()
            try: self._active_proc.wait(timeout=3)
            except: self._active_proc.kill()
        self.destroy()

    def _auto_install_osfmount(self):
        if not os.path.isfile(_OSFMOUNT_SETUP): return
        try:
            subprocess.Popen([_OSFMOUNT_SETUP, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                             creationflags=subprocess.CREATE_NO_WINDOW).wait()
        except: pass

    @staticmethod
    def _find_free_drive() -> str | None:
        try:
            r = subprocess.run(["wmic", "logicaldisk", "get", "Caption"],
                               capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            used = {l.strip()[0].upper() for l in r.stdout.splitlines() if l.strip() and ':' in l.strip()}
        except: used = set()
        for letter in reversed(string.ascii_uppercase):
            if letter not in used and letter not in ('A', 'B'): return letter + ':'
        return None


if __name__ == "__main__":
    app = App()
    app.mainloop()
