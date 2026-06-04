import customtkinter as ctk
import subprocess
import threading
import os
import re
import json
import time
import multiprocessing
from tkinter import filedialog

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VERSION = "0.0.2"

CONFIG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MkPFS Converter", "config.json")

# Regex para capturar linhas de progresso: [###---]  45% scan @ ...
_RE_PROGRESS = re.compile(r"\[[#\-]+\]\s+(\d+)%\s+(\w+)")


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
        self.title(f"MkPFS Converter v{VERSION}")
        self.geometry("720x660")
        self.resizable(False, False)

        self._cpu_count = multiprocessing.cpu_count()
        self._active_proc = None
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        cfg = _load_config()
        self._saved_cpus = int(cfg.get("cpu_count", self._cpu_count))

        self._t1_input_folder = ctk.StringVar()
        self._t1_temp_file    = ctk.StringVar(value=cfg.get("temp_file", ""))
        self._t1_output_file  = ctk.StringVar(value=cfg.get("t1_output_dir", ""))

        self._t2_source_file  = ctk.StringVar()
        self._t2_output_file  = ctk.StringVar(value=cfg.get("t2_output_dir", ""))

        self._build_ui()

    # ──────────────────────────────────────────────────────────
    #  UI principal
    # ──────────────────────────────────────────────────────────
    def _build_ui(self):
        ctk.CTkLabel(self, text="MkPFS Converter",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 4))
        ctk.CTkLabel(self, text=f"v{VERSION}",
                     font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(0, 10))

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self._tabs.add("Pasta > ffpfsc")
        self._tabs.add("exfat > ffpfsc")

        self._build_tab1(self._tabs.tab("Pasta > ffpfsc"))
        self._build_tab2(self._tabs.tab("exfat > ffpfsc"))

    # ──────────────────────────────────────────────────────────
    #  Tab 1
    # ──────────────────────────────────────────────────────────
    def _build_tab1(self, parent):
        pad = {"padx": 16, "pady": (8, 0)}

        self._tab_section(parent, "Passo 1 — Pasta de entrada")
        r1 = ctk.CTkFrame(parent, fg_color="transparent")
        r1.pack(fill="x", **pad)
        ctk.CTkEntry(r1, textvariable=self._t1_input_folder,
                     placeholder_text="Selecione a pasta com os arquivos...",
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

        # CPU slider
        self._tab_section(parent, "Núcleos de CPU")
        cpu_row = ctk.CTkFrame(parent, fg_color="transparent")
        cpu_row.pack(fill="x", padx=16, pady=(4, 0))
        self._t1_cpu_label = ctk.CTkLabel(cpu_row,
                                           text=f"{self._saved_cpus} / {self._cpu_count}",
                                           width=60)
        self._t1_cpu_label.pack(side="right")
        self._t1_cpu_slider = ctk.CTkSlider(cpu_row, from_=1, to=self._cpu_count,
                                             number_of_steps=self._cpu_count - 1,
                                             command=self._on_cpu_slider)
        self._t1_cpu_slider.set(self._saved_cpus)
        self._t1_cpu_slider.pack(side="left", fill="x", expand=True, padx=(0, 12))

        # Botão
        self._t1_btn = ctk.CTkButton(parent, text="Converter", height=40,
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     command=self._t1_start)
        self._t1_btn.pack(pady=(14, 0), padx=16, fill="x")

        # Progresso
        self._t1_phase_label = ctk.CTkLabel(parent, text="", anchor="w",
                                             font=ctk.CTkFont(size=12))
        self._t1_phase_label.pack(fill="x", padx=16, pady=(10, 2))
        self._t1_bar = ctk.CTkProgressBar(parent, height=18)
        self._t1_bar.set(0)
        self._t1_bar.pack(fill="x", padx=16)

        # Log
        ctk.CTkLabel(parent, text="Log", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self._t1_log = ctk.CTkTextbox(parent, height=130,
                                       font=ctk.CTkFont(family="Courier New", size=11),
                                       state="disabled")
        self._t1_log.pack(fill="both", expand=True, padx=16, pady=(0, 10))

    # ──────────────────────────────────────────────────────────
    #  Tab 2
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

        # CPU slider
        self._tab_section(parent, "Núcleos de CPU")
        cpu_row = ctk.CTkFrame(parent, fg_color="transparent")
        cpu_row.pack(fill="x", padx=16, pady=(4, 0))
        self._t2_cpu_label = ctk.CTkLabel(cpu_row,
                                           text=f"{self._saved_cpus} / {self._cpu_count}",
                                           width=60)
        self._t2_cpu_label.pack(side="right")
        self._t2_cpu_slider = ctk.CTkSlider(cpu_row, from_=1, to=self._cpu_count,
                                             number_of_steps=self._cpu_count - 1,
                                             command=self._on_cpu_slider)
        self._t2_cpu_slider.set(self._saved_cpus)
        self._t2_cpu_slider.pack(side="left", fill="x", expand=True, padx=(0, 12))

        # Botão
        self._t2_btn = ctk.CTkButton(parent, text="Converter", height=40,
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     command=self._t2_start)
        self._t2_btn.pack(pady=(14, 0), padx=16, fill="x")

        # Progresso
        self._t2_phase_label = ctk.CTkLabel(parent, text="", anchor="w",
                                             font=ctk.CTkFont(size=12))
        self._t2_phase_label.pack(fill="x", padx=16, pady=(10, 2))
        self._t2_bar = ctk.CTkProgressBar(parent, height=18)
        self._t2_bar.set(0)
        self._t2_bar.pack(fill="x", padx=16)

        # Log
        ctk.CTkLabel(parent, text="Log", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self._t2_log = ctk.CTkTextbox(parent, height=130,
                                       font=ctk.CTkFont(family="Courier New", size=11),
                                       state="disabled")
        self._t2_log.pack(fill="both", expand=True, padx=16, pady=(0, 10))

    def _tab_section(self, parent, title):
        ctk.CTkLabel(parent, text=title, anchor="w",
                     font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=16, pady=(12, 2))

    # ──────────────────────────────────────────────────────────
    #  CPU slider
    # ──────────────────────────────────────────────────────────
    def _on_cpu_slider(self, value):
        cpus = int(value)
        self._t1_cpu_label.configure(text=f"{cpus} / {self._cpu_count}")
        self._t2_cpu_label.configure(text=f"{cpus} / {self._cpu_count}")
        self._t1_cpu_slider.set(cpus)
        self._t2_cpu_slider.set(cpus)
        _save_config({**_load_config(), "cpu_count": cpus})

    # ──────────────────────────────────────────────────────────
    #  Tab 1 — pickers
    # ──────────────────────────────────────────────────────────
    def _t1_pick_folder(self):
        path = filedialog.askdirectory(title="Selecione a pasta de entrada")
        if path:
            self._t1_input_folder.set(path)
            folder_name = os.path.basename(path.rstrip("/\\"))
            if not self._t1_temp_file.get():
                self._t1_temp_file.set(os.path.join(path, "pfs_image.dat"))
            output_dir = os.path.dirname(self._t1_output_file.get()) if self._t1_output_file.get() else path
            self._t1_output_file.set(os.path.join(output_dir, f"{folder_name}.ffpfsc"))

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
            output_dir = os.path.dirname(self._t2_output_file.get()) if self._t2_output_file.get() else os.path.dirname(path)
            self._t2_output_file.set(os.path.join(output_dir, f"{base}.ffpfsc"))

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
    #  Tab 1 — conversão
    # ──────────────────────────────────────────────────────────
    def _t1_start(self):
        folder = self._t1_input_folder.get().strip()
        temp   = self._t1_temp_file.get().strip()
        output = self._t1_output_file.get().strip()

        if not folder or not os.path.isdir(folder):
            self._log_append(self._t1_log, "[ERRO] Selecione uma pasta de entrada válida.\n", clear=True)
            return
        if not temp:
            self._log_append(self._t1_log, "[ERRO] Informe o caminho do arquivo temporário.\n", clear=True)
            return
        if not output:
            self._log_append(self._t1_log, "[ERRO] Informe o caminho do arquivo de saída.\n", clear=True)
            return

        cpus = int(self._t1_cpu_slider.get())
        self._t1_btn.configure(state="disabled", text="Convertendo...")
        self._t1_bar.set(0)
        self._t1_phase_label.configure(text="")
        self._log_clear(self._t1_log)
        self._t1_start_time = time.time()
        threading.Thread(target=self._t1_run, args=(folder, temp, output, cpus), daemon=True).start()

    def _t1_run(self, folder, temp, output, cpus):
        if os.path.exists(temp):
            os.remove(temp)

        cmd1 = [
            "mkpfs", "pack", "folder",
            "--no-compress", "--no-adjust-output-file-extension",
            "--version", "PS5", "--inode-bits", "32",
            "--cpu-count", str(cpus),
            folder, temp,
        ]
        temp_dir = os.path.dirname(os.path.abspath(temp))
        cmd2 = [
            "mkpfs", "pack", "file",
            "--version", "PS5", "--inode-bits", "32",
            "--cpu-count", str(cpus),
            "--temp-folder", temp_dir,
            temp, output,
        ]

        success = self._run_cmd(cmd1, self._t1_bar, self._t1_phase_label,
                                 self._t1_log, step_prefix="Passo 1/2")
        if success:
            success = self._run_cmd(cmd2, self._t1_bar, self._t1_phase_label,
                                     self._t1_log, step_prefix="Passo 2/2")

        if os.path.exists(temp):
            try:
                os.remove(temp)
            except Exception:
                pass

        elapsed = time.time() - self._t1_start_time
        elapsed_str = self._fmt_elapsed(elapsed)
        if success:
            self.after(0, lambda s=elapsed_str: self._t1_phase_label.configure(
                text=f"✓ Concluído em {s}", text_color="#a3e635"))
        else:
            self.after(0, lambda s=elapsed_str: self._t1_phase_label.configure(
                text=f"✗ Falhou após {s}", text_color="#f87171"))

        self.after(0, lambda: self._t1_btn.configure(state="normal", text="Converter"))

    # ──────────────────────────────────────────────────────────
    #  Tab 2 — conversão
    # ──────────────────────────────────────────────────────────
    def _t2_start(self):
        source = self._t2_source_file.get().strip()
        output = self._t2_output_file.get().strip()

        if not source or not os.path.isfile(source):
            self._log_append(self._t2_log, "[ERRO] Selecione um arquivo .exfat válido.\n", clear=True)
            return
        if not output:
            self._log_append(self._t2_log, "[ERRO] Informe o caminho do arquivo de saída.\n", clear=True)
            return

        cpus = int(self._t2_cpu_slider.get())
        self._t2_btn.configure(state="disabled", text="Convertendo...")
        self._t2_bar.set(0)
        self._t2_phase_label.configure(text="")
        self._log_clear(self._t2_log)
        self._t2_start_time = time.time()
        threading.Thread(target=self._t2_run, args=(source, output, cpus), daemon=True).start()

    def _t2_run(self, source, output, cpus):
        temp_dir = os.path.dirname(os.path.abspath(source))
        cmd = [
            "mkpfs", "pack", "file",
            "--version", "PS5", "--inode-bits", "32",
            "--cpu-count", str(cpus),
            "--temp-folder", temp_dir,
            source, output,
        ]

        success = self._run_cmd(cmd, self._t2_bar, self._t2_phase_label,
                                 self._t2_log, step_prefix="")

        elapsed = time.time() - self._t2_start_time
        elapsed_str = self._fmt_elapsed(elapsed)
        if success:
            self.after(0, lambda s=elapsed_str: self._t2_phase_label.configure(
                text=f"✓ Concluído em {s}", text_color="#a3e635"))
        else:
            self.after(0, lambda s=elapsed_str: self._t2_phase_label.configure(
                text=f"✗ Falhou após {s}", text_color="#f87171"))

        self.after(0, lambda: self._t2_btn.configure(state="normal", text="Converter"))

    # ──────────────────────────────────────────────────────────
    #  Core: roda comando, separa progresso do log
    # ──────────────────────────────────────────────────────────
    def _run_cmd(self, cmd: list, bar: ctk.CTkProgressBar,
                 phase_label: ctk.CTkLabel, log: ctk.CTkTextbox,
                 step_prefix: str) -> bool:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._active_proc = proc

            for line in proc.stdout:
                m = _RE_PROGRESS.search(line)
                if m:
                    # Linha de progresso → atualiza barra e label, NÃO vai pro log
                    pct   = int(m.group(1)) / 100.0
                    phase = m.group(2).capitalize()
                    label_text = f"{step_prefix} — {phase}  {int(pct * 100)}%" if step_prefix else f"{phase}  {int(pct * 100)}%"
                    self.after(0, lambda v=pct, t=label_text: (
                        bar.set(v),
                        phase_label.configure(text=t, text_color="white"),
                    ))
                else:
                    # Linha real de output → vai pro log
                    stripped = line.rstrip("\n")
                    if stripped:
                        self.after(0, lambda l=stripped: self._log_append(log, l + "\n"))

            proc.stdout.close()
            proc.wait()
            self._active_proc = None
            return proc.returncode == 0
        except FileNotFoundError:
            self.after(0, lambda: self._log_append(log, "[ERRO] mkpfs não encontrado.\n"))
            return False
        except Exception as e:
            self.after(0, lambda: self._log_append(log, f"[ERRO] {e}\n"))
            return False

    # ──────────────────────────────────────────────────────────
    #  Log helpers
    # ──────────────────────────────────────────────────────────
    def _log_append(self, widget: ctk.CTkTextbox, text: str, clear: bool = False):
        widget.configure(state="normal")
        if clear:
            widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.see("end")
        widget.configure(state="disabled")

    def _log_clear(self, widget: ctk.CTkTextbox):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _fmt_elapsed(self, seconds: float) -> str:
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        if m:
            return f"{m}m {s:02d}s"
        return f"{s}s"

    # ──────────────────────────────────────────────────────────
    #  Fechar janela
    # ──────────────────────────────────────────────────────────
    def _on_close(self):
        if self._active_proc and self._active_proc.poll() is None:
            self._active_proc.terminate()
            try:
                self._active_proc.wait(timeout=3)
            except Exception:
                self._active_proc.kill()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
