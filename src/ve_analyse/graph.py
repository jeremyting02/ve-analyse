"""Data preparation helpers for log graphing."""

from __future__ import annotations

from dataclasses import dataclass

from .datalog import DataLog


@dataclass(frozen=True)
class PlotSeries:
    name: str
    points: list[tuple[float, float]]
    minimum: float
    maximum: float


def detect_time_column(log: DataLog) -> str | None:
    normalized = {_normalize(column): column for column in log.columns}
    return normalized.get("time")


def numeric_columns(log: DataLog) -> list[str]:
    columns: list[str] = []
    for column in log.columns:
        if _numeric_values(log, column):
            columns.append(column)
    return columns


def build_plot_series(
    log: DataLog,
    variables: list[str],
    *,
    time_column: str | None = None,
    max_points_per_series: int = 2500,
) -> list[PlotSeries]:
    """Build graphable time/value series for selected variables."""

    time_column = time_column or detect_time_column(log)
    series: list[PlotSeries] = []
    for variable in variables:
        points: list[tuple[float, float]] = []
        for index, row in enumerate(log.rows):
            value = _as_float(row.get(variable))
            if value is None:
                continue
            time_value = _as_float(row.get(time_column)) if time_column else None
            points.append((time_value if time_value is not None else float(index), value))
        if not points:
            continue
        points = _downsample(points, max_points_per_series)
        values = [value for _, value in points]
        series.append(
            PlotSeries(
                name=variable,
                points=points,
                minimum=min(values),
                maximum=max(values),
            )
        )
    return series


def _numeric_values(log: DataLog, column: str) -> list[float]:
    values: list[float] = []
    for row in log.rows:
        value = _as_float(row.get(column))
        if value is not None:
            values.append(value)
    return values


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _downsample(points: list[tuple[float, float]], max_points: int) -> list[tuple[float, float]]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    stride = max(1, len(points) // max_points)
    sampled = points[::stride]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def _normalize(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())

