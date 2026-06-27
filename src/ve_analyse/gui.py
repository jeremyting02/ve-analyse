"""Small Tkinter UI for VE Analyse."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .analyzer import AnalyzerConfig, analyze
from .datalog import parse_datalog
from .table import format_table, parse_table


class VeAnalyseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("VE Analyse")
        self.geometry("820x620")
        self.minsize(720, 520)
        self.log_paths: list[Path] = []

        self.ve_path = tk.StringVar()
        self.afr_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.min_clt = tk.StringVar(value="60")
        self.max_tpsacc = tk.StringVar(value="110")
        self.min_samples = tk.StringVar(value="3")
        self.authority = tk.StringVar(value="1.0")
        self.max_cell_change = tk.StringVar(value="0.15")
        self.afr_0v = tk.StringVar(value="10")
        self.afr_5v = tk.StringVar(value="20")

        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        files = ttk.Frame(self, padding=12)
        files.grid(row=0, column=0, sticky="ew")
        files.columnconfigure(1, weight=1)

        ttk.Label(files, text="Data logs").grid(row=0, column=0, sticky="w")
        log_buttons = ttk.Frame(files)
        log_buttons.grid(row=0, column=1, sticky="w")
        ttk.Button(log_buttons, text="Add", command=self._add_logs).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(log_buttons, text="Clear", command=self._clear_logs).grid(row=0, column=1)

        self.log_list = tk.Listbox(files, height=4)
        self.log_list.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 10))

        self._file_row(files, 2, "VE table", self.ve_path, self._choose_ve)
        self._file_row(files, 3, "AFR target", self.afr_path, self._choose_afr)
        self._file_row(files, 4, "Output", self.output_path, self._choose_output)

        params = ttk.LabelFrame(self, text="Parameters", padding=12)
        params.grid(row=1, column=0, sticky="ew", padx=12)
        for col in range(6):
            params.columnconfigure(col, weight=1)

        self._entry(params, 0, 0, "Min CLT", self.min_clt)
        self._entry(params, 0, 2, "Max TPSacc", self.max_tpsacc)
        self._entry(params, 0, 4, "Min samples", self.min_samples)
        self._entry(params, 1, 0, "Authority", self.authority)
        self._entry(params, 1, 2, "Max cell change", self.max_cell_change)
        self._entry(params, 1, 4, "AFR at 0/5 V", self.afr_0v, self.afr_5v)

        output = ttk.Frame(self, padding=12)
        output.grid(row=2, column=0, sticky="nsew")
        output.columnconfigure(0, weight=1)
        output.rowconfigure(0, weight=1)
        self.summary = tk.Text(output, height=12, wrap="word")
        self.summary.grid(row=0, column=0, sticky="nsew")

        actions = ttk.Frame(self, padding=(12, 0, 12, 12))
        actions.grid(row=3, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(actions, text="Analyse", command=self._run)
        self.run_button.grid(row=0, column=1, sticky="e")

    def _file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=3)
        ttk.Button(parent, text="Browse", command=command).grid(row=row, column=2, pady=3)

    def _entry(
        self,
        parent: ttk.LabelFrame,
        row: int,
        col: int,
        label: str,
        first: tk.StringVar,
        second: tk.StringVar | None = None,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(0, 6), pady=4)
        if second is None:
            ttk.Entry(parent, textvariable=first, width=8).grid(row=row, column=col + 1, sticky="w", pady=4)
            return
        pair = ttk.Frame(parent)
        pair.grid(row=row, column=col + 1, sticky="w", pady=4)
        ttk.Entry(pair, textvariable=first, width=8).grid(row=0, column=0, padx=(0, 4))
        ttk.Entry(pair, textvariable=second, width=8).grid(row=0, column=1)

    def _add_logs(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Choose data logs",
            filetypes=[("Data logs", "*.msl *.csv *.tsv *.txt"), ("All files", "*.*")],
        )
        for path in paths:
            path_obj = Path(path)
            if path_obj not in self.log_paths:
                self.log_paths.append(path_obj)
                self.log_list.insert(tk.END, str(path_obj))

    def _clear_logs(self) -> None:
        self.log_paths.clear()
        self.log_list.delete(0, tk.END)

    def _choose_ve(self) -> None:
        self._choose_file(self.ve_path, "Choose VE table")

    def _choose_afr(self) -> None:
        self._choose_file(self.afr_path, "Choose AFR target table")

    def _choose_file(self, variable: tk.StringVar, title: str) -> None:
        path = filedialog.askopenfilename(
            title=title,
            filetypes=[("Tables", "*.tsv *.csv *.txt *.ve *.afr"), ("All files", "*.*")],
        )
        if path:
            variable.set(path)

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Choose output VE table",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.output_path.set(path)

    def _run(self) -> None:
        if not self.log_paths:
            messagebox.showerror("VE Analyse", "Add at least one data log.")
            return
        if not self.ve_path.get() or not self.afr_path.get() or not self.output_path.get():
            messagebox.showerror("VE Analyse", "Choose VE, AFR target and output files.")
            return

        self.run_button.configure(state=tk.DISABLED)
        self._set_summary("Analysing...\n")
        worker = threading.Thread(target=self._run_worker, daemon=True)
        worker.start()

    def _run_worker(self) -> None:
        try:
            config = AnalyzerConfig(
                min_clt=_optional_float(self.min_clt.get()),
                max_tpsacc=_optional_float(self.max_tpsacc.get()),
                min_samples_per_cell=int(self.min_samples.get()),
                authority=float(self.authority.get()),
                max_cell_change=float(self.max_cell_change.get()),
                wideband_afr_at_0v=float(self.afr_0v.get()),
                wideband_afr_at_5v=float(self.afr_5v.get()),
            )
            logs = [parse_datalog(path) for path in self.log_paths]
            ve_table = parse_table(Path(self.ve_path.get()))
            afr_table = parse_table(Path(self.afr_path.get()))
            result = analyze(logs, ve_table, afr_table, config)
            Path(self.output_path.get()).write_text(
                format_table(result.table, decimals=config.output_decimals),
                encoding="utf-8",
            )
            self.after(0, lambda: self._finish(result.summary_text()))
        except Exception as exc:
            self.after(0, lambda: self._fail(exc))

    def _finish(self, summary: str) -> None:
        self._set_summary(summary)
        self.run_button.configure(state=tk.NORMAL)

    def _fail(self, exc: Exception) -> None:
        self.run_button.configure(state=tk.NORMAL)
        messagebox.showerror("VE Analyse", str(exc))
        self._set_summary(f"Failed:\n{exc}\n")

    def _set_summary(self, text: str) -> None:
        self.summary.configure(state=tk.NORMAL)
        self.summary.delete("1.0", tk.END)
        self.summary.insert(tk.END, text)
        self.summary.configure(state=tk.NORMAL)


def _optional_float(value: str) -> float | None:
    cleaned = value.strip().lower()
    if cleaned in {"", "none", "off", "null"}:
        return None
    return float(cleaned)


def main() -> int:
    app = VeAnalyseApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
