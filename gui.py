import customtkinter as ctk
import subprocess
import threading
import os
import json
import multiprocessing
from tkinter import filedialog

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VERSION = "0.0.1"

CONFIG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MkPFS Converter", "config.json")


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

        # ── Aba 1: Pasta > ffpfsc ──────────────────────────────
        self._t1_input_folder = ctk.StringVar()
        self._t1_temp_file    = ctk.StringVar(value=cfg.get("temp_file", ""))
        self._t1_output_file  = ctk.StringVar(value=cfg.get("t1_output_dir", ""))

        # ── Aba 2: exfat > ffpfsc ─────────────────────────────
        self._t2_source_file  = ctk.StringVar()
        self._t2_output_file  = ctk.StringVar(value=cfg.get("t2_output_dir", ""))

        self._build_ui()

    # ──────────────────────────────────────────────────────────
    #  UI
    # ──────────────────────────────────────────────────────────
    def _build_ui(self):
        # Título
        ctk.CTkLabel(self, text="MkPFS Converter", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 4))
        ctk.CTkLabel(self, text=f"v{VERSION}", font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(0, 10))

        # TabView
        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._tabs.add("Pasta > ffpfsc")
        self._tabs.add("exfat > ffpfsc")

        self._build_tab1(self._tabs.tab("Pasta > ffpfsc"))
        self._build_tab2(self._tabs.tab("exfat > ffpfsc"))

    # ── Tab 1 ─────────────────────────────────────────────────
    def _build_tab1(self, parent):
        pad = {"padx": 16, "pady": (10, 0)}

        self._tab_section(parent, "Passo 1 — Pasta de entrada")
        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(fill="x", **pad)
        ctk.CTkEntry(row1, textvariable=self._t1_input_folder, placeholder_text="Selecione a pasta com os arquivos...", width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row1, text="Selecionar", width=110, command=self._t1_pick_folder).pack(side="left")

        self._tab_section(parent, "Passo 2 — Arquivo temporário (pfs_image.dat)")
        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", **pad)
        ctk.CTkEntry(row2, textvariable=self._t1_temp_file, placeholder_text="Onde salvar pfs_image.dat...", width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row2, text="Selecionar", width=110, command=self._t1_pick_temp).pack(side="left")

        self._tab_section(parent, "Passo 3 — Arquivo de saída (.ffpfsc)")
        row3 = ctk.CTkFrame(parent, fg_color="transparent")
        row3.pack(fill="x", **pad)
        ctk.CTkEntry(row3, textvariable=self._t1_output_file, placeholder_text="Nome e local do arquivo final .ffpfsc...", width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row3, text="Selecionar", width=110, command=self._t1_pick_output).pack(side="left")

        self._tab_section(parent, "Núcleos de CPU para conversão")
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
        self._t1_btn.pack(pady=(16, 0), padx=16, fill="x")

        ctk.CTkLabel(parent, text="Log", anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        self._t1_log = ctk.CTkTextbox(parent, height=160, font=ctk.CTkFont(family="Courier New", size=11), state="disabled")
        self._t1_log.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    # ── Tab 2 ─────────────────────────────────────────────────
    def _build_tab2(self, parent):
        pad = {"padx": 16, "pady": (10, 0)}

        self._tab_section(parent, "Arquivo de origem (.exfat)")
        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(fill="x", **pad)
        ctk.CTkEntry(row1, textvariable=self._t2_source_file, placeholder_text="Selecione o arquivo .exfat...", width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row1, text="Selecionar", width=110, command=self._t2_pick_source).pack(side="left")

        self._tab_section(parent, "Arquivo de saída (.ffpfsc)")
        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", **pad)
        ctk.CTkEntry(row2, textvariable=self._t2_output_file, placeholder_text="Nome e local do arquivo final .ffpfsc...", width=490).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row2, text="Selecionar", width=110, command=self._t2_pick_output).pack(side="left")

        self._tab_section(parent, "Núcleos de CPU para conversão")
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
        self._t2_btn.pack(pady=(16, 0), padx=16, fill="x")

        ctk.CTkLabel(parent, text="Log", anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        self._t2_log = ctk.CTkTextbox(parent, height=160, font=ctk.CTkFont(family="Courier New", size=11), state="disabled")
        self._t2_log.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _tab_section(self, parent, title: str):
        ctk.CTkLabel(parent, text=title, anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=16, pady=(14, 2))

    # ──────────────────────────────────────────────────────────
    #  CPU slider (compartilhado)
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
            self._log_write(self._t1_log, "[ERRO] Selecione uma pasta de entrada válida.\n", clear=True)
            return
        if not temp:
            self._log_write(self._t1_log, "[ERRO] Informe o caminho do arquivo temporário.\n", clear=True)
            return
        if not output:
            self._log_write(self._t1_log, "[ERRO] Informe o caminho do arquivo de saída.\n", clear=True)
            return

        cpus = int(self._t1_cpu_slider.get())
        self._t1_btn.configure(state="disabled", text="Convertendo...")
        self._log_clear(self._t1_log)
        threading.Thread(target=self._t1_run, args=(folder, temp, output, cpus), daemon=True).start()

    def _t1_run(self, folder, temp, output, cpus):
        if os.path.exists(temp):
            os.remove(temp)

        cmd1 = [
            "mkpfs", "pack", "folder",
            "--no-compress",
            "--no-adjust-output-file-extension",
            "--version", "PS5",
            "--inode-bits", "32",
            "--cpu-count", str(cpus),
            folder, temp,
        ]
        temp_dir = os.path.dirname(os.path.abspath(temp))
        cmd2 = [
            "mkpfs", "pack", "file",
            "--version", "PS5",
            "--inode-bits", "32",
            "--cpu-count", str(cpus),
            "--temp-folder", temp_dir,
            temp, output,
        ]

        success = self._run_cmd(self._t1_log, "Passo 1/2 — pack folder", cmd1)
        if success:
            success = self._run_cmd(self._t1_log, "Passo 2/2 — pack file", cmd2)

        if os.path.exists(temp):
            try:
                os.remove(temp)
                self._log_write(self._t1_log, f"\n🗑 Arquivo temporário removido: {temp}\n")
            except Exception as e:
                self._log_write(self._t1_log, f"\n[AVISO] Não foi possível remover o temporário: {e}\n")

        if success:
            self._log_write(self._t1_log, "\n✓ Conversão concluída com sucesso!\n")
            self._log_write(self._t1_log, f"  Arquivo gerado: {output}\n")
        else:
            self._log_write(self._t1_log, "\n✗ Conversão falhou. Verifique o log acima.\n")

        self.after(0, lambda: self._t1_btn.configure(state="normal", text="Converter"))

    # ──────────────────────────────────────────────────────────
    #  Tab 2 — conversão
    # ──────────────────────────────────────────────────────────
    def _t2_start(self):
        source = self._t2_source_file.get().strip()
        output = self._t2_output_file.get().strip()

        if not source or not os.path.isfile(source):
            self._log_write(self._t2_log, "[ERRO] Selecione um arquivo .exfat válido.\n", clear=True)
            return
        if not output:
            self._log_write(self._t2_log, "[ERRO] Informe o caminho do arquivo de saída.\n", clear=True)
            return

        cpus = int(self._t2_cpu_slider.get())
        self._t2_btn.configure(state="disabled", text="Convertendo...")
        self._log_clear(self._t2_log)
        threading.Thread(target=self._t2_run, args=(source, output, cpus), daemon=True).start()

    def _t2_run(self, source, output, cpus):
        temp_dir = os.path.dirname(os.path.abspath(source))
        cmd = [
            "mkpfs", "pack", "file",
            "--version", "PS5",
            "--inode-bits", "32",
            "--cpu-count", str(cpus),
            "--temp-folder", temp_dir,
            source, output,
        ]

        success = self._run_cmd(self._t2_log, "exfat > ffpfsc", cmd)

        if success:
            self._log_write(self._t2_log, "\n✓ Conversão concluída com sucesso!\n")
            self._log_write(self._t2_log, f"  Arquivo gerado: {output}\n")
        else:
            self._log_write(self._t2_log, "\n✗ Conversão falhou. Verifique o log acima.\n")

        self.after(0, lambda: self._t2_btn.configure(state="normal", text="Converter"))

    # ──────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────
    def _on_close(self):
        if self._active_proc and self._active_proc.poll() is None:
            self._active_proc.terminate()
            try:
                self._active_proc.wait(timeout=3)
            except Exception:
                self._active_proc.kill()
        self.destroy()

    def _log_write(self, widget, text: str, clear: bool = False):
        widget.configure(state="normal")
        if clear:
            widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.see("end")
        widget.configure(state="disabled")

    def _log_clear(self, widget):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _run_cmd(self, log_widget, label: str, cmd: list) -> bool:
        self._log_write(log_widget, f"\n── {label} ──\n")
        self._log_write(log_widget, f"$ {' '.join(cmd)}\n\n")
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
                self._log_write(log_widget, line)
            proc.stdout.close()
            proc.wait()
            self._active_proc = None
            return proc.returncode == 0
        except FileNotFoundError:
            self._log_write(log_widget, "[ERRO] Comando 'mkpfs' não encontrado. Verifique a instalação.\n")
            return False
        except Exception as e:
            self._log_write(log_widget, f"[ERRO] {e}\n")
            return False


if __name__ == "__main__":
    app = App()
    app.mainloop()
