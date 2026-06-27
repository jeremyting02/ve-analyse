"""Request helpers for the local web UI."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .analyzer import AnalyzerConfig, analyze
from .datalog import parse_datalog
from .graph import build_plot_series, detect_time_column, numeric_columns
from .state import UiState, load_ui_state, save_ui_state
from .table import GridTable, format_table, parse_table


DEFAULT_WEB_PARAMETERS: dict[str, str] = {
    "min_rpm": "400",
    "min_clt": "60",
    "max_clt": "",
    "min_pw": "0.5",
    "max_tpsacc": "110",
    "min_gego": "",
    "max_gego": "",
    "authority": "1.0",
    "max_sample_correction": "0.25",
    "max_cell_change": "0.15",
    "min_samples": "3",
    "min_cell_weight": "0",
    "smoothing_passes": "0",
    "smoothing_factor": "0.20",
    "afr_0v": "10",
    "afr_5v": "20",
    "output_decimals": "2",
    "distribution": "bilinear",
    "out_of_bounds": "skip",
}


def state_payload(path: Path | None = None) -> dict[str, Any]:
    state = load_ui_state(path)
    payload = asdict(state)
    parameters = dict(DEFAULT_WEB_PARAMETERS)
    parameters.update(state.parameters)
    payload["parameters"] = parameters
    return payload


def save_state_payload(payload: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    state = UiState(
        log_paths=_string_list(payload.get("log_paths")),
        ve_path=_as_string(payload.get("ve_path")),
        afr_path=_as_string(payload.get("afr_path")),
        output_path=_as_string(payload.get("output_path")),
        parameters=_string_dict(payload.get("parameters")),
        graph_log=_as_string(payload.get("graph_log")),
        graph_variables=_string_list(payload.get("graph_variables")),
        graph_groups=_dict_list(payload.get("graph_groups")),
        active_graph_id=_as_string(payload.get("active_graph_id")),
        graph_zoom=_plain_dict(payload.get("graph_zoom")),
        active_tab=_as_string(payload.get("active_tab")) or "Graphs",
        geometry=_as_string(payload.get("geometry")),
    )
    save_ui_state(state, path)
    return state_payload(path)


def log_metadata(path: str) -> dict[str, Any]:
    log = parse_datalog(Path(path))
    columns = numeric_columns(log)
    return {
        "path": path,
        "source": log.source,
        "columns": log.columns,
        "numeric_columns": columns,
        "time_column": detect_time_column(log),
        "row_count": len(log.rows),
    }


def graph_payload(path: str, variables: list[str], max_points_per_series: int = 2500) -> dict[str, Any]:
    log = parse_datalog(Path(path))
    series = build_plot_series(
        log,
        variables,
        max_points_per_series=max_points_per_series,
    )
    all_times = [time for item in series for time, _value in item.points]
    return {
        "path": path,
        "row_count": len(log.rows),
        "time_column": detect_time_column(log),
        "x_min": min(all_times) if all_times else 0.0,
        "x_max": max(all_times) if all_times else 1.0,
        "series": [
            {
                "name": item.name,
                "minimum": item.minimum,
                "maximum": item.maximum,
                "points": item.points,
            }
            for item in series
        ],
    }


def analyse_payload(payload: dict[str, Any]) -> dict[str, Any]:
    log_paths = _string_list(payload.get("log_paths"))
    if not log_paths:
        raise ValueError("Add at least one data log.")

    ve_path = _required_path(payload.get("ve_path"), "VE table")
    afr_path = _required_path(payload.get("afr_path"), "AFR target table")
    output_path = _required_path(payload.get("output_path"), "output VE table")
    parameters = _string_dict(payload.get("parameters"))
    config = config_from_parameters(parameters)

    logs = [parse_datalog(Path(path)) for path in log_paths]
    ve_table = parse_table(ve_path)
    afr_table = parse_table(afr_path)
    result = analyze(logs, ve_table, afr_table, config)
    output_csv = format_table(result.table, decimals=config.output_decimals)
    output_saved = True
    output_error = ""
    try:
        output_path.write_text(output_csv, encoding="utf-8")
    except OSError as exc:
        output_saved = False
        output_error = str(exc)

    updates = []
    for update in result.updates:
        delta_percent = 0.0
        if update.old_ve:
            delta_percent = (update.new_ve / update.old_ve - 1.0) * 100.0
        updates.append(
            {
                "rpm": update.rpm_bin,
                "load": update.map_bin,
                "old_ve": update.old_ve,
                "new_ve": update.new_ve,
                "delta_percent": delta_percent,
                "samples": update.samples,
                "weight": update.weight,
            }
        )

    return {
        "summary": result.summary_dict(),
        "summary_text": result.summary_text(),
        "updates": updates,
        "tables": {
            "old": table_payload(ve_table),
            "new": table_payload(result.table),
        },
        "output_path": str(output_path),
        "output_saved": output_saved,
        "output_error": output_error,
        "output_csv": output_csv,
        "output_filename": output_path.name or "ve-new.csv",
    }


def table_payload(table: GridTable) -> dict[str, Any]:
    """Return a display table with RPM ascending and MAP/load descending."""

    x_order = sorted(range(len(table.x_bins)), key=lambda index: table.x_bins[index])
    y_order = sorted(range(len(table.y_bins)), key=lambda index: table.y_bins[index], reverse=True)
    return {
        "x_label": table.x_label,
        "y_label": table.y_label,
        "x_bins": [table.x_bins[index] for index in x_order],
        "y_bins": [table.y_bins[index] for index in y_order],
        "values": [
            [table.values[row_index][col_index] for col_index in x_order]
            for row_index in y_order
        ],
    }


def config_from_parameters(parameters: dict[str, str]) -> AnalyzerConfig:
    values = dict(DEFAULT_WEB_PARAMETERS)
    values.update(parameters)
    return AnalyzerConfig(
        min_rpm=_float(values.get("min_rpm"), 400.0) or 400.0,
        min_clt=_optional_float(values.get("min_clt")),
        max_clt=_optional_float(values.get("max_clt")),
        min_pw=_optional_float(values.get("min_pw")),
        max_tpsacc=_optional_float(values.get("max_tpsacc")),
        min_gego=_optional_float(values.get("min_gego")),
        max_gego=_optional_float(values.get("max_gego")),
        wideband_afr_at_0v=_float(values.get("afr_0v"), 10.0) or 10.0,
        wideband_afr_at_5v=_float(values.get("afr_5v"), 20.0) or 20.0,
        out_of_bounds="clamp" if values.get("out_of_bounds") == "clamp" else "skip",
        distribution="nearest" if values.get("distribution") == "nearest" else "bilinear",
        min_samples_per_cell=int(_float(values.get("min_samples"), 3) or 3),
        min_cell_weight=_float(values.get("min_cell_weight"), 0.0) or 0.0,
        authority=_float(values.get("authority"), 1.0) or 1.0,
        max_sample_correction=_float(values.get("max_sample_correction"), 0.25) or 0.25,
        max_cell_change=_float(values.get("max_cell_change"), 0.15) or 0.15,
        smoothing_passes=int(_float(values.get("smoothing_passes"), 0) or 0),
        smoothing_factor=_float(values.get("smoothing_factor"), 0.20) or 0.20,
        output_decimals=int(_float(values.get("output_decimals"), 2) or 2),
    )


def _required_path(value: Any, label: str) -> Path:
    raw_path = _as_string(value).strip()
    if not raw_path:
        raise ValueError(f"Choose a {label}.")
    return Path(raw_path)


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if cleaned in {"", "none", "off", "null"}:
        return None
    return float(cleaned)


def _float(value: str | None, fallback: float) -> float | None:
    try:
        return _optional_float(value)
    except ValueError:
        return fallback


def _as_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: str(item)
        for key, item in value.items()
        if isinstance(key, str)
    }


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _plain_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
