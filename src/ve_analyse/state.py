"""Persistent UI state for VE Analyse."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


STATE_VERSION = 1


@dataclass
class UiState:
    version: int = STATE_VERSION
    log_paths: list[str] = field(default_factory=list)
    ve_path: str = ""
    afr_path: str = ""
    output_path: str = ""
    parameters: dict[str, str] = field(default_factory=dict)
    graph_log: str = ""
    graph_variables: list[str] = field(default_factory=list)
    graph_groups: list[dict[str, Any]] = field(default_factory=list)
    active_graph_id: str = ""
    graph_zoom: dict[str, Any] = field(default_factory=dict)
    active_tab: str = "Analyse"
    geometry: str = ""


def default_state_path() -> Path:
    app_data = os.environ.get("APPDATA")
    if app_data:
        return Path(app_data) / "VE Analyse" / "state.json"
    return Path.home() / ".ve-analyse" / "state.json"


def load_ui_state(path: Path | None = None) -> UiState:
    state_path = path or default_state_path()
    if not state_path.exists():
        return UiState()

    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return UiState()

    if not isinstance(raw, dict):
        return UiState()

    return UiState(
        version=_as_int(raw.get("version"), STATE_VERSION),
        log_paths=_string_list(raw.get("log_paths")),
        ve_path=_as_string(raw.get("ve_path")),
        afr_path=_as_string(raw.get("afr_path")),
        output_path=_as_string(raw.get("output_path")),
        parameters=_string_dict(raw.get("parameters")),
        graph_log=_as_string(raw.get("graph_log")),
        graph_variables=_string_list(raw.get("graph_variables")),
        graph_groups=_dict_list(raw.get("graph_groups")),
        active_graph_id=_as_string(raw.get("active_graph_id")),
        graph_zoom=_plain_dict(raw.get("graph_zoom")),
        active_tab=_as_string(raw.get("active_tab")) or "Analyse",
        geometry=_as_string(raw.get("geometry")),
    )


def save_ui_state(state: UiState, path: Path | None = None) -> None:
    state_path = path or default_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True), encoding="utf-8")


def _as_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) else fallback


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _plain_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
