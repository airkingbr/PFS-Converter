import customtkinter as ctk
import subprocess
import threading
import os
import json
import multiprocessing
from tkinter import filedialog

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

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
        self.title("MkPFS Converter")
        self.geometry("720x620")
        self.resizable(False, False)

        self._input_folder = ctk.StringVar()
        self._temp_file = ctk.StringVar()
        self._output_file = ctk.StringVar()
        self._cpu_count = multiprocessing.cpu_count()

        cfg = _load_config()
        if cfg.get("temp_file"):
            self._temp_file.set(cfg["temp_file"])
        if cfg.get("output_dir"):
            self._output_file.set(cfg["output_dir"])
        self._saved_cpus = int(cfg.get("cpu_count", self._cpu_count))

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 20, "pady": (10, 0)}

        # ── Title ──────────────────────────────────────────────
        ctk.CTkLabel(self, text="MkPFS Converter", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))

        # ── Step 1: Input Folder ───────────────────────────────
        self._section("Passo 1 — Pasta de entrada")
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", **pad)
        ctk.CTkEntry(row1, textvariable=self._input_folder, placeholder_text="Selecione a pasta com os arquivos...", width=540).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row1, text="Selecionar", width=110, command=self._pick_folder).pack(side="left")

        # ── Step 2: Temp File ──────────────────────────────────
        self._section("Passo 2 — Arquivo temporário (pfs_image.dat)")
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", **pad)
        ctk.CTkEntry(row2, textvariable=self._temp_file, placeholder_text="Onde salvar pfs_image.dat...", width=540).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row2, text="Selecionar", width=110, command=self._pick_temp).pack(side="left")

        # ── Step 3: Output File ────────────────────────────────
        self._section("Passo 3 — Arquivo de saída (.ffpfsc)")
        row3 = ctk.CTkFrame(self, fg_color="transparent")
        row3.pack(fill="x", **pad)
        ctk.CTkEntry(row3, textvariable=self._output_file, placeholder_text="Nome e local do arquivo final .ffpfsc...", width=540).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row3, text="Selecionar", width=110, command=self._pick_output).pack(side="left")

        # ── CPU Slider ────────────────────────────────────────────
        self._section("Núcleos de CPU para conversão")
        cpu_row = ctk.CTkFrame(self, fg_color="transparent")
        cpu_row.pack(fill="x", padx=20, pady=(4, 0))

        self._cpu_label = ctk.CTkLabel(cpu_row, text=f"{self._saved_cpus} / {self._cpu_count}", width=60)
        self._cpu_label.pack(side="right")

        self._cpu_slider = ctk.CTkSlider(
            cpu_row, from_=1, to=self._cpu_count,
            number_of_steps=self._cpu_count - 1,
            command=self._on_cpu_slider,
        )
        self._cpu_slider.set(self._saved_cpus)
        self._cpu_slider.pack(side="left", fill="x", expand=True, padx=(0, 12))

        # ── Convert Button ─────────────────────────────────────
        self._btn_convert = ctk.CTkButton(
            self, text="Converter", height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start_conversion
        )
        self._btn_convert.pack(pady=(24, 0), padx=20, fill="x")

        # ── Log ────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Log", anchor="w").pack(fill="x", padx=20, pady=(16, 4))
        self._log = ctk.CTkTextbox(self, height=200, font=ctk.CTkFont(family="Courier New", size=12), state="disabled")
        self._log.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    def _on_cpu_slider(self, value):
        cpus = int(value)
        self._cpu_label.configure(text=f"{cpus} / {self._cpu_count}")
        _save_config({**_load_config(), "cpu_count": cpus})

    def _section(self, title: str):
        ctk.CTkLabel(self, text=title, anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=(14, 2))

    # ── File pickers ───────────────────────────────────────────
    def _pick_folder(self):
        path = filedialog.askdirectory(title="Selecione a pasta de entrada")
        if path:
            self._input_folder.set(path)
            if not self._temp_file.get():
                self._temp_file.set(os.path.join(path, "pfs_image.dat"))

    def _pick_temp(self):
        current = self._temp_file.get()
        initial_dir = os.path.dirname(current) if current else None
        path = filedialog.asksaveasfilename(
            title="Local do arquivo temporário",
            defaultextension=".dat",
            filetypes=[("DAT file", "*.dat"), ("All files", "*.*")],
            initialfile="pfs_image.dat",
            initialdir=initial_dir,
        )
        if path:
            self._temp_file.set(path)
            _save_config({**_load_config(), "temp_file": path})

    def _pick_output(self):
        current = self._output_file.get()
        initial_dir = os.path.dirname(current) if current else None
        path = filedialog.asksaveasfilename(
            title="Salvar arquivo final como",
            defaultextension=".ffpfsc",
            filetypes=[("FFPFSC file", "*.ffpfsc")],
            initialdir=initial_dir,
        )
        if path:
            if not path.endswith(".ffpfsc"):
                path = os.path.splitext(path)[0] + ".ffpfsc"
            self._output_file.set(path)
            _save_config({**_load_config(), "output_dir": os.path.dirname(path)})

    # ── Log helpers ────────────────────────────────────────────
    def _log_write(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _log_clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    # ── Conversion ─────────────────────────────────────────────
    def _start_conversion(self):
        folder = self._input_folder.get().strip()
        temp = self._temp_file.get().strip()
        output = self._output_file.get().strip()

        if not folder or not os.path.isdir(folder):
            self._log_clear()
            self._log_write("[ERRO] Selecione uma pasta de entrada válida.\n")
            return
        if not temp:
            self._log_clear()
            self._log_write("[ERRO] Informe o caminho do arquivo temporário.\n")
            return
        if not output:
            self._log_clear()
            self._log_write("[ERRO] Informe o caminho do arquivo de saída.\n")
            return

        cpus = int(self._cpu_slider.get())
        self._btn_convert.configure(state="disabled", text="Convertendo...")
        self._log_clear()
        threading.Thread(target=self._run_conversion, args=(folder, temp, output, cpus), daemon=True).start()

    def _run_conversion(self, folder: str, temp: str, output: str, cpus: int):
        if os.path.exists(temp):
            os.remove(temp)

        cmd1 = [
            "mkpfs", "pack", "folder",
            "--verify", "--no-compress",
            "--no-adjust-output-file-extension",
            "--version", "PS5",
            "--inode-bits", "32",
            "--cpu-count", str(cpus),
            folder, temp,
        ]
        # --temp-folder must be on the same drive as pfs_image.dat so that
        # mkpfs can create a hard link without crossing drive boundaries.
        temp_dir = os.path.dirname(os.path.abspath(temp))
        cmd2 = [
            "mkpfs", "pack", "file",
            "--verify",
            "--version", "PS5",
            "--inode-bits", "32",
            "--cpu-count", str(cpus),
            "--temp-folder", temp_dir,
            temp, output,
        ]

        success = self._run_cmd("Passo 1/2 — pack folder", cmd1)
        if success:
            success = self._run_cmd("Passo 2/2 — pack file", cmd2)

        if success:
            self._log_write("\n✓ Conversão concluída com sucesso!\n")
            self._log_write(f"  Arquivo gerado: {output}\n")
        else:
            self._log_write("\n✗ Conversão falhou. Verifique o log acima.\n")

        self.after(0, lambda: self._btn_convert.configure(state="normal", text="Converter"))

    def _run_cmd(self, label: str, cmd: list) -> bool:
        self._log_write(f"\n── {label} ──\n")
        self._log_write(f"$ {' '.join(cmd)}\n\n")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in proc.stdout:
                self._log_write(line)
            proc.stdout.close()
            proc.wait()
            return proc.returncode == 0
        except FileNotFoundError:
            self._log_write("[ERRO] Comando 'mkpfs' não encontrado. Verifique a instalação.\n")
            return False
        except Exception as e:
            self._log_write(f"[ERRO] {e}\n")
            return False


if __name__ == "__main__":
    app = App()
    app.mainloop()
