"""VE table analyser core."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Literal

from .datalog import DataLog
from .table import GridTable, OutOfBoundsMode, cell_weights


DistributionMode = Literal["bilinear", "nearest"]


@dataclass
class AnalyzerConfig:
    rpm_column: str | None = None
    map_column: str | None = None
    o2_column: str | None = None
    time_column: str | None = None
    clt_column: str | None = None
    tpsacc_column: str | None = None
    pw_column: str | None = None
    gego_column: str | None = None

    o2_is_afr: bool = False
    wideband_afr_at_0v: float = 10.0
    wideband_afr_at_5v: float = 20.0

    min_rpm: float = 400.0
    min_clt: float | None = 60.0
    max_clt: float | None = None
    min_pw: float | None = 0.5
    max_tpsacc: float | None = 110.0
    min_gego: float | None = None
    max_gego: float | None = None

    out_of_bounds: OutOfBoundsMode = "skip"
    distribution: DistributionMode = "bilinear"
    weight_by_time: bool = False
    max_time_weight: float = 0.5

    min_samples_per_cell: int = 3
    min_cell_weight: float = 0.0
    authority: float = 1.0
    min_sample_authority: float = 0.35
    full_authority_samples: int = 30
    max_sample_correction: float = 0.25
    max_cell_change: float = 0.15
    smoothing_passes: int = 0
    smoothing_factor: float = 0.20
    output_decimals: int = 2

    def wideband_afr(self, voltage: float) -> float:
        slope = (self.wideband_afr_at_5v - self.wideband_afr_at_0v) / 5.0
        return self.wideband_afr_at_0v + voltage * slope


@dataclass
class CellUpdate:
    row: int
    col: int
    map_bin: float
    rpm_bin: float
    old_ve: float
    new_ve: float
    correction: float
    samples: int
    weight: float


@dataclass
class AnalysisResult:
    table: GridTable
    updates: list[CellUpdate]
    accepted_rows: int
    skipped_rows: int
    skip_reasons: dict[str, int] = field(default_factory=dict)
    logs_processed: int = 0

    def summary_dict(self) -> dict[str, object]:
        changed = sum(1 for update in self.updates if not math.isclose(update.old_ve, update.new_ve))
        max_change = 0.0
        for update in self.updates:
            if update.old_ve:
                max_change = max(max_change, abs(update.new_ve / update.old_ve - 1.0))
        return {
            "logs_processed": self.logs_processed,
            "accepted_rows": self.accepted_rows,
            "skipped_rows": self.skipped_rows,
            "cells_updated": len(self.updates),
            "cells_changed": changed,
            "max_change_fraction": max_change,
            "skip_reasons": dict(sorted(self.skip_reasons.items())),
        }

    def summary_text(self) -> str:
        summary = self.summary_dict()
        lines = [
            f"Logs processed: {summary['logs_processed']}",
            f"Rows accepted: {summary['accepted_rows']}",
            f"Rows skipped: {summary['skipped_rows']}",
            f"Cells updated: {summary['cells_updated']}",
            f"Cells changed: {summary['cells_changed']}",
            f"Max cell change: {float(summary['max_change_fraction']) * 100:.1f}%",
        ]
        reasons = summary["skip_reasons"]
        if reasons:
            lines.append("Skip reasons:")
            lines.extend(f"  {reason}: {count}" for reason, count in reasons.items())
        return "\n".join(lines)

    def summary_json(self) -> str:
        return json.dumps(self.summary_dict(), indent=2, sort_keys=True)


@dataclass
class _CellAccumulator:
    weighted_log_sum: float = 0.0
    weight: float = 0.0
    samples: int = 0

    def add(self, correction: float, weight: float) -> None:
        if correction <= 0 or weight <= 0:
            return
        self.weighted_log_sum += math.log(correction) * weight
        self.weight += weight
        self.samples += 1

    @property
    def correction(self) -> float:
        if self.weight <= 0:
            return 1.0
        return math.exp(self.weighted_log_sum / self.weight)


def analyze(
    logs: list[DataLog],
    ve_table: GridTable,
    afr_target_table: GridTable,
    config: AnalyzerConfig | None = None,
) -> AnalysisResult:
    """Analyse log rows and return a new VE table."""

    config = config or AnalyzerConfig()
    accumulators = [
        [_CellAccumulator() for _ in range(ve_table.width)]
        for _ in range(ve_table.height)
    ]
    accepted_rows = 0
    skipped_rows = 0
    skip_reasons: dict[str, int] = {}

    for log in logs:
        columns = _ResolvedColumns.from_log(log, config)
        previous_time: float | None = None
        for row in log.numeric_rows():
            row_time = _number(row.get(columns.time)) if columns.time else None
            sample, reason = _sample_from_row(row, columns, config, previous_time)
            if row_time is not None:
                previous_time = row_time
            if sample is None:
                skipped_rows += 1
                _add_reason(skip_reasons, reason or "invalid")
                continue

            target_afr = afr_target_table.interpolate(
                sample.rpm,
                sample.map_kpa,
                out_of_bounds=config.out_of_bounds,
            )
            if target_afr is None or target_afr <= 0:
                skipped_rows += 1
                _add_reason(skip_reasons, "outside_afr_table")
                continue

            weights = cell_weights(
                ve_table.x_bins,
                ve_table.y_bins,
                sample.rpm,
                sample.map_kpa,
                out_of_bounds=config.out_of_bounds,
                mode=config.distribution,
            )
            if not weights:
                skipped_rows += 1
                _add_reason(skip_reasons, "outside_ve_table")
                continue

            correction = sample.measured_afr / target_afr
            correction = _limit_ratio(correction, config.max_sample_correction)
            for row_index, col_index, cell_weight in weights:
                accumulators[row_index][col_index].add(correction, cell_weight * sample.weight)
            accepted_rows += 1

    new_values = [list(row) for row in ve_table.values]
    updates: list[CellUpdate] = []

    for row_index, row in enumerate(accumulators):
        for col_index, accumulator in enumerate(row):
            if accumulator.samples < config.min_samples_per_cell:
                continue
            if accumulator.weight < config.min_cell_weight:
                continue

            correction = _limit_ratio(accumulator.correction, config.max_cell_change)
            sample_confidence = _sample_confidence(
                accumulator.samples,
                min_samples=config.min_samples_per_cell,
                min_sample_authority=config.min_sample_authority,
                full_authority_samples=config.full_authority_samples,
            )
            applied = 1.0 + (correction - 1.0) * config.authority * sample_confidence
            old_ve = ve_table.values[row_index][col_index]
            new_ve = max(0.0, old_ve * applied)
            new_values[row_index][col_index] = new_ve
            updates.append(
                CellUpdate(
                    row=row_index,
                    col=col_index,
                    map_bin=ve_table.y_bins[row_index],
                    rpm_bin=ve_table.x_bins[col_index],
                    old_ve=old_ve,
                    new_ve=new_ve,
                    correction=applied,
                    samples=accumulator.samples,
                    weight=accumulator.weight,
                )
            )

    if config.smoothing_passes > 0 and updates:
        touched = {(update.row, update.col) for update in updates}
        new_values = _smooth_touched_cells(
            new_values,
            touched,
            passes=config.smoothing_passes,
            factor=config.smoothing_factor,
        )
        update_by_cell = {(update.row, update.col): update for update in updates}
        for (row_index, col_index), update in update_by_cell.items():
            update.new_ve = new_values[row_index][col_index]

    rounded_values = [
        [round(value, config.output_decimals) for value in row]
        for row in new_values
    ]
    rounded_table = ve_table.copy_with_values(rounded_values)
    for update in updates:
        update.new_ve = round(update.new_ve, config.output_decimals)

    return AnalysisResult(
        table=rounded_table,
        updates=updates,
        accepted_rows=accepted_rows,
        skipped_rows=skipped_rows,
        skip_reasons=skip_reasons,
        logs_processed=len(logs),
    )


@dataclass
class _ResolvedColumns:
    rpm: str
    rpm_multiplier: float
    map_kpa: str
    o2: str
    time: str | None
    clt: str | None
    tpsacc: str | None
    pw: str | None
    gego: str | None

    @classmethod
    def from_log(cls, log: DataLog, config: AnalyzerConfig) -> "_ResolvedColumns":
        rpm_column = config.rpm_column or _pick_column(log.columns, ["RPM", "rpm"])
        rpm_multiplier = 1.0
        if rpm_column is None:
            rpm_column = _pick_column(log.columns, ["RPM/100", "rpm/100"])
            rpm_multiplier = 100.0
        if rpm_column is None:
            raise ValueError(f"Could not resolve RPM column in {log.source or 'data log'}")

        return cls(
            rpm=rpm_column,
            rpm_multiplier=100.0 if rpm_column.lower() == "rpm/100" else rpm_multiplier,
            map_kpa=config.map_column or _require_column(log.columns, ["MAP", "map"]),
            o2=config.o2_column or _require_column(log.columns, ["O2", "AFR", "afr"]),
            time=config.time_column or _pick_column(log.columns, ["Time", "time"]),
            clt=config.clt_column or _pick_column(log.columns, ["CLT", "Coolant"]),
            tpsacc=config.tpsacc_column or _pick_column(log.columns, ["TPSacc", "TPS Accel"]),
            pw=config.pw_column or _pick_column(log.columns, ["PW", "PulseWidth", "Pulse Width"]),
            gego=config.gego_column or _pick_column(log.columns, ["Gego", "EGO"]),
        )


@dataclass
class _Sample:
    rpm: float
    map_kpa: float
    measured_afr: float
    weight: float
    current_time: float | None


def _sample_from_row(
    row: dict[str, float | str],
    columns: _ResolvedColumns,
    config: AnalyzerConfig,
    previous_time: float | None,
) -> tuple[_Sample | None, str | None]:
    rpm_value = _number(row.get(columns.rpm))
    map_value = _number(row.get(columns.map_kpa))
    o2_value = _number(row.get(columns.o2))
    if rpm_value is None or map_value is None or o2_value is None:
        return None, "missing_required_value"

    rpm = rpm_value * columns.rpm_multiplier
    if rpm < config.min_rpm:
        return None, "below_min_rpm"

    if config.min_clt is not None and columns.clt:
        clt = _number(row.get(columns.clt))
        if clt is not None and clt < config.min_clt:
            return None, "below_min_clt"
    if config.max_clt is not None and columns.clt:
        clt = _number(row.get(columns.clt))
        if clt is not None and clt > config.max_clt:
            return None, "above_max_clt"

    if config.min_pw is not None and columns.pw:
        pw = _number(row.get(columns.pw))
        if pw is not None and pw < config.min_pw:
            return None, "below_min_pw"

    if config.max_tpsacc is not None and columns.tpsacc:
        tpsacc = _number(row.get(columns.tpsacc))
        if tpsacc is not None and tpsacc > config.max_tpsacc:
            return None, "above_max_tpsacc"

    if config.min_gego is not None and columns.gego:
        gego = _number(row.get(columns.gego))
        if gego is not None and gego < config.min_gego:
            return None, "below_min_gego"
    if config.max_gego is not None and columns.gego:
        gego = _number(row.get(columns.gego))
        if gego is not None and gego > config.max_gego:
            return None, "above_max_gego"

    measured_afr = o2_value if config.o2_is_afr else config.wideband_afr(o2_value)
    if measured_afr <= 0 or not math.isfinite(measured_afr):
        return None, "invalid_afr"

    current_time = _number(row.get(columns.time)) if columns.time else None
    weight = 1.0
    if config.weight_by_time:
        if current_time is None or previous_time is None:
            weight = 0.0
        else:
            weight = max(0.0, min(config.max_time_weight, current_time - previous_time))
    if weight <= 0:
        return None, "zero_weight"

    return _Sample(
        rpm=rpm,
        map_kpa=map_value,
        measured_afr=measured_afr,
        weight=weight,
        current_time=current_time,
    ), None


def _pick_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {_normalize(column): column for column in columns}
    for candidate in candidates:
        found = normalized.get(_normalize(candidate))
        if found:
            return found
    for candidate in candidates:
        candidate_norm = _normalize(candidate)
        for column in columns:
            if candidate_norm in _normalize(column):
                return column
    return None


def _require_column(columns: list[str], candidates: list[str]) -> str:
    column = _pick_column(columns, candidates)
    if column is None:
        raise ValueError(f"Could not find any of these columns: {', '.join(candidates)}")
    return column


def _normalize(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _number(value: float | str | None) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    cleaned = str(value).strip().replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _limit_ratio(ratio: float, max_change: float) -> float:
    if max_change < 0:
        raise ValueError("max change must be non-negative")
    return min(1.0 + max_change, max(1.0 - max_change, ratio))


def _sample_confidence(
    samples: int,
    *,
    min_samples: int,
    min_sample_authority: float,
    full_authority_samples: int,
) -> float:
    if samples < min_samples:
        return 0.0
    floor = min(1.0, max(0.0, min_sample_authority))
    if full_authority_samples <= min_samples:
        return 1.0
    progress = (samples - min_samples) / (full_authority_samples - min_samples)
    return min(1.0, max(floor, progress))


def _smooth_touched_cells(
    values: list[list[float]],
    touched: set[tuple[int, int]],
    *,
    passes: int,
    factor: float,
) -> list[list[float]]:
    factor = min(1.0, max(0.0, factor))
    current = [list(row) for row in values]
    height = len(current)
    width = len(current[0]) if height else 0
    for _ in range(max(0, passes)):
        next_values = [list(row) for row in current]
        for row, col in touched:
            neighbours: list[float] = []
            for row_delta, col_delta in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                n_row = row + row_delta
                n_col = col + col_delta
                if 0 <= n_row < height and 0 <= n_col < width:
                    neighbours.append(current[n_row][n_col])
            if neighbours:
                average = sum(neighbours) / len(neighbours)
                next_values[row][col] = current[row][col] * (1.0 - factor) + average * factor
        current = next_values
    return current


def _add_reason(reasons: dict[str, int], reason: str) -> None:
    reasons[reason] = reasons.get(reason, 0) + 1


def config_to_dict(config: AnalyzerConfig) -> dict[str, object]:
    return asdict(config)
