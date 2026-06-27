"""Small Tkinter UI for VE Analyse."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .analyzer import AnalyzerConfig, analyze
from .datalog import DataLog, parse_datalog
from .graph import PlotSeries, build_plot_series, numeric_columns
from .state import UiState, load_ui_state, save_ui_state
from .table import format_table, parse_table


class VeAnalyseApp(tk.Tk):
    def __init__(self, state_path: Path | None = None) -> None:
        super().__init__()
        self.state_path = state_path
        self.ui_state = load_ui_state(state_path)
        self._restoring_state = True
        self.title("VE Analyse")
        self._set_initial_geometry(self.ui_state.geometry)
        self.minsize(720, 520)
        self.log_paths: list[Path] = [Path(path) for path in self.ui_state.log_paths]
        self.parsed_logs: dict[Path, DataLog] = {}
        parameters = self.ui_state.parameters

        self.ve_path = tk.StringVar(value=self.ui_state.ve_path)
        self.afr_path = tk.StringVar(value=self.ui_state.afr_path)
        self.output_path = tk.StringVar(value=self.ui_state.output_path)
        self.min_clt = tk.StringVar(value=parameters.get("min_clt", "60"))
        self.max_tpsacc = tk.StringVar(value=parameters.get("max_tpsacc", "110"))
        self.min_samples = tk.StringVar(value=parameters.get("min_samples", "3"))
        self.authority = tk.StringVar(value=parameters.get("authority", "1.0"))
        self.max_cell_change = tk.StringVar(value=parameters.get("max_cell_change", "0.15"))
        self.afr_0v = tk.StringVar(value=parameters.get("afr_0v", "10"))
        self.afr_5v = tk.StringVar(value=parameters.get("afr_5v", "20"))
        self.graph_log = tk.StringVar(value=self.ui_state.graph_log)
        self.graph_status = tk.StringVar(value="")
        self.graph_series: list[PlotSeries] = []
        self.graph_palette = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]

        self._build()
        self._restore_state_to_widgets()
        self._restoring_state = False
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_initial_geometry(self, geometry: str) -> None:
        try:
            self.geometry(geometry or "820x620")
        except tk.TclError:
            self.geometry("820x620")

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        analyse_tab = ttk.Frame(self.notebook)
        graph_tab = ttk.Frame(self.notebook)
        self.notebook.add(analyse_tab, text="Analyse")
        self.notebook.add(graph_tab, text="Graph")

        self._build_analyse_tab(analyse_tab)
        self._build_graph_tab(graph_tab)
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self._save_state())

    def _build_analyse_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        files = ttk.Frame(parent, padding=12)
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

        params = ttk.LabelFrame(parent, text="Parameters", padding=12)
        params.grid(row=1, column=0, sticky="ew", padx=12)
        for col in range(6):
            params.columnconfigure(col, weight=1)

        self._entry(params, 0, 0, "Min CLT", self.min_clt)
        self._entry(params, 0, 2, "Max TPSacc", self.max_tpsacc)
        self._entry(params, 0, 4, "Min samples", self.min_samples)
        self._entry(params, 1, 0, "Authority", self.authority)
        self._entry(params, 1, 2, "Max cell change", self.max_cell_change)
        self._entry(params, 1, 4, "AFR at 0/5 V", self.afr_0v, self.afr_5v)

        output = ttk.Frame(parent, padding=12)
        output.grid(row=2, column=0, sticky="nsew")
        output.columnconfigure(0, weight=1)
        output.rowconfigure(0, weight=1)
        self.summary = tk.Text(output, height=12, wrap="word")
        self.summary.grid(row=0, column=0, sticky="nsew")

        actions = ttk.Frame(parent, padding=(12, 0, 12, 12))
        actions.grid(row=3, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(actions, text="Analyse", command=self._run)
        self.run_button.grid(row=0, column=1, sticky="e")

    def _build_graph_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent, padding=12)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        ttk.Label(toolbar, text="Log").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.graph_log_combo = ttk.Combobox(toolbar, textvariable=self.graph_log, state="readonly")
        self.graph_log_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.graph_log_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_graph_log_changed())
        ttk.Button(toolbar, text="Load variables", command=self._load_graph_variables).grid(row=0, column=2)

        sidebar = ttk.Frame(parent, padding=(12, 0, 6, 12))
        sidebar.grid(row=1, column=0, sticky="ns")
        sidebar.rowconfigure(1, weight=1)
        ttk.Label(sidebar, text="Variables").grid(row=0, column=0, sticky="w", pady=(0, 4))
        variable_frame = ttk.Frame(sidebar)
        variable_frame.grid(row=1, column=0, sticky="ns")
        variable_frame.rowconfigure(0, weight=1)
        self.graph_variable_list = tk.Listbox(
            variable_frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            width=24,
            height=20,
        )
        self.graph_variable_list.grid(row=0, column=0, sticky="ns")
        variable_scroll = ttk.Scrollbar(variable_frame, orient=tk.VERTICAL, command=self.graph_variable_list.yview)
        variable_scroll.grid(row=0, column=1, sticky="ns")
        self.graph_variable_list.configure(yscrollcommand=variable_scroll.set)
        self.graph_variable_list.bind("<<ListboxSelect>>", lambda _event: self._plot_selected_variables())

        graph_buttons = ttk.Frame(sidebar)
        graph_buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(graph_buttons, text="Plot", command=self._plot_selected_variables).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(graph_buttons, text="Clear", command=self._clear_graph_selection).grid(row=0, column=1)

        graph_area = ttk.Frame(parent, padding=(6, 0, 12, 12))
        graph_area.grid(row=1, column=1, sticky="nsew")
        graph_area.columnconfigure(0, weight=1)
        graph_area.rowconfigure(0, weight=1)
        self.graph_canvas = tk.Canvas(graph_area, bg="#ffffff", highlightthickness=1, highlightbackground="#c9ced6")
        self.graph_canvas.grid(row=0, column=0, sticky="nsew")
        self.graph_canvas.bind("<Configure>", lambda _event: self._draw_graph())
        ttk.Label(graph_area, textvariable=self.graph_status).grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _restore_state_to_widgets(self) -> None:
        self.log_list.delete(0, tk.END)
        for path in self.log_paths:
            self.log_list.insert(tk.END, str(path))
        self._refresh_graph_logs()
        if self.ui_state.graph_log:
            self.graph_log.set(self.ui_state.graph_log)
        self._restore_active_tab()
        if self.ui_state.graph_variables and self._selected_graph_path() is not None:
            self._load_graph_variables(selected_variables=self.ui_state.graph_variables, silent=True)

    def _restore_active_tab(self) -> None:
        target = self.ui_state.active_tab
        for tab_id in self.notebook.tabs():
            if self.notebook.tab(tab_id, "text") == target:
                self.notebook.select(tab_id)
                return

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
        self._refresh_graph_logs()
        self._save_state()

    def _clear_logs(self) -> None:
        self.log_paths.clear()
        self.parsed_logs.clear()
        self.log_list.delete(0, tk.END)
        self.graph_log.set("")
        self._refresh_graph_logs()
        self.graph_variable_list.delete(0, tk.END)
        self.graph_series = []
        self.graph_status.set("")
        self._draw_graph()
        self._save_state()

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
            self._save_state()

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Choose output VE table",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.output_path.set(path)
            self._save_state()

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
        self._save_state()

    def _fail(self, exc: Exception) -> None:
        self.run_button.configure(state=tk.NORMAL)
        messagebox.showerror("VE Analyse", str(exc))
        self._set_summary(f"Failed:\n{exc}\n")
        self._save_state()

    def _set_summary(self, text: str) -> None:
        self.summary.configure(state=tk.NORMAL)
        self.summary.delete("1.0", tk.END)
        self.summary.insert(tk.END, text)
        self.summary.configure(state=tk.NORMAL)

    def _refresh_graph_logs(self) -> None:
        values = [str(path) for path in self.log_paths]
        self.graph_log_combo.configure(values=values)
        if not values:
            self.graph_log.set("")
            return
        if self.graph_log.get() not in values:
            self.graph_log.set(values[0])

    def _on_graph_log_changed(self) -> None:
        self.graph_variable_list.delete(0, tk.END)
        self.graph_series = []
        self.graph_status.set("")
        self._draw_graph()
        self._save_state()

    def _selected_graph_path(self) -> Path | None:
        selected = self.graph_log.get()
        if selected:
            return Path(selected)
        if self.log_paths:
            return self.log_paths[0]
        return None

    def _get_graph_log(self) -> DataLog:
        path = self._selected_graph_path()
        if path is None:
            raise ValueError("Add a data log before opening the graph.")
        if path not in self.parsed_logs:
            self.parsed_logs[path] = parse_datalog(path)
        return self.parsed_logs[path]

    def _load_graph_variables(
        self,
        selected_variables: list[str] | None = None,
        *,
        silent: bool = False,
    ) -> None:
        try:
            log = self._get_graph_log()
        except Exception as exc:
            if not silent:
                messagebox.showerror("VE Analyse", str(exc))
            else:
                self.graph_status.set(str(exc))
            return

        columns = numeric_columns(log)
        self.graph_variable_list.delete(0, tk.END)
        for column in columns:
            self.graph_variable_list.insert(tk.END, column)

        preferred = {"rpm", "map", "o2", "afr", "pw", "sparkangle"}
        for index, column in enumerate(columns):
            normalized = "".join(character.lower() for character in column if character.isalnum())
            if selected_variables and column in selected_variables:
                self.graph_variable_list.selection_set(index)
            elif not selected_variables and normalized in preferred:
                self.graph_variable_list.selection_set(index)

        self._plot_selected_variables()
        self._save_state()

    def _plot_selected_variables(self) -> None:
        if self.graph_variable_list.size() == 0 and self.log_paths:
            self._load_graph_variables()
            return

        selected = [
            self.graph_variable_list.get(index)
            for index in self.graph_variable_list.curselection()
        ]
        if not selected:
            self.graph_series = []
            self.graph_status.set("")
            self._draw_graph()
            self._save_state()
            return

        try:
            log = self._get_graph_log()
            self.graph_series = build_plot_series(log, selected)
            point_count = sum(len(series.points) for series in self.graph_series)
            self.graph_status.set(f"{len(self.graph_series)} variables, {point_count} plotted points")
            self._draw_graph()
            self._save_state()
        except Exception as exc:
            messagebox.showerror("VE Analyse", str(exc))

    def _clear_graph_selection(self) -> None:
        self.graph_variable_list.selection_clear(0, tk.END)
        self.graph_series = []
        self.graph_status.set("")
        self._draw_graph()
        self._save_state()

    def _current_tab_name(self) -> str:
        selected = self.notebook.select()
        return self.notebook.tab(selected, "text") if selected else "Analyse"

    def _selected_graph_variables(self) -> list[str]:
        return [
            self.graph_variable_list.get(index)
            for index in self.graph_variable_list.curselection()
        ]

    def _build_ui_state(self) -> UiState:
        return UiState(
            log_paths=[str(path) for path in self.log_paths],
            ve_path=self.ve_path.get(),
            afr_path=self.afr_path.get(),
            output_path=self.output_path.get(),
            parameters={
                "min_clt": self.min_clt.get(),
                "max_tpsacc": self.max_tpsacc.get(),
                "min_samples": self.min_samples.get(),
                "authority": self.authority.get(),
                "max_cell_change": self.max_cell_change.get(),
                "afr_0v": self.afr_0v.get(),
                "afr_5v": self.afr_5v.get(),
            },
            graph_log=self.graph_log.get(),
            graph_variables=self._selected_graph_variables(),
            active_tab=self._current_tab_name(),
            geometry=self.geometry(),
        )

    def _save_state(self) -> None:
        if self._restoring_state:
            return
        try:
            save_ui_state(self._build_ui_state(), self.state_path)
        except OSError:
            pass

    def _on_close(self) -> None:
        self._save_state()
        self.destroy()

    def _draw_graph(self) -> None:
        canvas = getattr(self, "graph_canvas", None)
        if canvas is None:
            return

        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        left = 64
        right = 164
        top = 22
        bottom = 42
        plot_left = left
        plot_right = max(left + 10, width - right)
        plot_top = top
        plot_bottom = max(top + 10, height - bottom)
        plot_width = plot_right - plot_left
        plot_height = plot_bottom - plot_top

        canvas.create_rectangle(plot_left, plot_top, plot_right, plot_bottom, outline="#c9ced6")
        for step in range(1, 5):
            y = plot_top + plot_height * step / 5
            canvas.create_line(plot_left, y, plot_right, y, fill="#edf0f4")
        for step in range(1, 6):
            x = plot_left + plot_width * step / 6
            canvas.create_line(x, plot_top, x, plot_bottom, fill="#f4f6f8")

        if not self.graph_series:
            canvas.create_text(
                (plot_left + plot_right) / 2,
                (plot_top + plot_bottom) / 2,
                text="No variables selected",
                fill="#6b7280",
            )
            return

        all_times = [time for series in self.graph_series for time, _value in series.points]
        x_min = min(all_times)
        x_max = max(all_times)
        if x_min == x_max:
            x_max = x_min + 1.0

        for step in range(0, 7):
            fraction = step / 6
            x = plot_left + plot_width * fraction
            value = x_min + (x_max - x_min) * fraction
            canvas.create_text(x, plot_bottom + 16, text=_format_tick(value), fill="#4b5563", font=("TkDefaultFont", 8))

        canvas.create_text(20, plot_top + 6, text="100%", fill="#4b5563", anchor="w", font=("TkDefaultFont", 8))
        canvas.create_text(20, plot_bottom - 6, text="0%", fill="#4b5563", anchor="w", font=("TkDefaultFont", 8))
        canvas.create_text((plot_left + plot_right) / 2, height - 12, text="Time", fill="#374151", font=("TkDefaultFont", 8))

        for index, series in enumerate(self.graph_series):
            color = self.graph_palette[index % len(self.graph_palette)]
            points = self._canvas_points(series, x_min, x_max, plot_left, plot_top, plot_width, plot_height)
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2)
            legend_y = plot_top + 18 + index * 34
            legend_x = plot_right + 18
            canvas.create_line(legend_x, legend_y, legend_x + 24, legend_y, fill=color, width=3)
            canvas.create_text(legend_x + 30, legend_y - 7, text=series.name, fill="#111827", anchor="nw")
            canvas.create_text(
                legend_x + 30,
                legend_y + 9,
                text=f"{_format_tick(series.minimum)} to {_format_tick(series.maximum)}",
                fill="#6b7280",
                anchor="nw",
                font=("TkDefaultFont", 8),
            )

    def _canvas_points(
        self,
        series: PlotSeries,
        x_min: float,
        x_max: float,
        plot_left: int,
        plot_top: int,
        plot_width: int,
        plot_height: int,
    ) -> list[float]:
        points: list[float] = []
        y_span = series.maximum - series.minimum
        x_span = x_max - x_min
        for time_value, value in series.points:
            x = plot_left + ((time_value - x_min) / x_span) * plot_width
            if y_span == 0:
                y_fraction = 0.5
            else:
                y_fraction = (value - series.minimum) / y_span
            y = plot_top + (1.0 - y_fraction) * plot_height
            points.extend([x, y])
        return points


def _optional_float(value: str) -> float | None:
    cleaned = value.strip().lower()
    if cleaned in {"", "none", "off", "null"}:
        return None
    return float(cleaned)


def _format_tick(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{value:.2f}".rstrip("0").rstrip(".")


def main() -> int:
    app = VeAnalyseApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
