"""Grid table parsing, interpolation and formatting."""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

OutOfBoundsMode = Literal["skip", "clamp"]


@dataclass(frozen=True)
class GridTable:
    x_bins: list[float]
    y_bins: list[float]
    values: list[list[float]]
    x_label: str = "RPM"
    y_label: str = "MAP"
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.x_bins:
            raise ValueError("Grid table must have at least one x/RPM bin")
        if not self.y_bins:
            raise ValueError("Grid table must have at least one y/load bin")
        if len(self.values) != len(self.y_bins):
            raise ValueError("Grid table row count does not match y/load bins")
        for row in self.values:
            if len(row) != len(self.x_bins):
                raise ValueError("Grid table column count does not match x/RPM bins")

    @property
    def width(self) -> int:
        return len(self.x_bins)

    @property
    def height(self) -> int:
        return len(self.y_bins)

    def copy_with_values(self, values: list[list[float]]) -> "GridTable":
        return GridTable(
            x_bins=list(self.x_bins),
            y_bins=list(self.y_bins),
            values=[list(row) for row in values],
            x_label=self.x_label,
            y_label=self.y_label,
            source=self.source,
        )

    def interpolate(self, x: float, y: float, *, out_of_bounds: OutOfBoundsMode = "skip") -> float | None:
        x_bracket = axis_bracket(self.x_bins, x, out_of_bounds=out_of_bounds)
        y_bracket = axis_bracket(self.y_bins, y, out_of_bounds=out_of_bounds)
        if x_bracket is None or y_bracket is None:
            return None

        x0, x1, tx = x_bracket
        y0, y1, ty = y_bracket

        if x0 == x1 and y0 == y1:
            return self.values[y0][x0]
        if x0 == x1:
            return _lerp(self.values[y0][x0], self.values[y1][x0], ty)
        if y0 == y1:
            return _lerp(self.values[y0][x0], self.values[y0][x1], tx)

        v00 = self.values[y0][x0]
        v10 = self.values[y0][x1]
        v01 = self.values[y1][x0]
        v11 = self.values[y1][x1]
        top = _lerp(v00, v10, tx)
        bottom = _lerp(v01, v11, tx)
        return _lerp(top, bottom, ty)


def parse_table(path_or_text: str | Path, *, source: str | None = None) -> GridTable:
    """Parse an RPM-by-load matrix from a path or text."""

    if isinstance(path_or_text, Path) or _looks_like_path(str(path_or_text)):
        path = Path(path_or_text)
        text = _read_text(path)
        source_name = source or str(path)
    else:
        text = str(path_or_text)
        source_name = source

    rows = [_tokenize(line) for line in text.splitlines() if line.strip()]
    header_index = _find_table_header(rows)
    if header_index is None:
        raise ValueError("Could not find a table header row with numeric RPM bins")

    header = rows[header_index]
    x_start = _x_start(header)
    x_bins = [_require_float(token, "RPM bin") for token in header[x_start:]]
    label = header[0] if x_start == 1 and header else "MAP/RPM"
    y_label, x_label = _split_axis_label(label)

    y_bins: list[float] = []
    values: list[list[float]] = []
    for tokens in rows[header_index + 1 :]:
        if len(tokens) < len(x_bins) + 1:
            continue
        y_value = _parse_float(tokens[0])
        if y_value is None:
            continue
        row_values: list[float] = []
        for token in tokens[1 : len(x_bins) + 1]:
            value = _parse_float(token)
            if value is None:
                break
            row_values.append(value)
        if len(row_values) != len(x_bins):
            continue
        y_bins.append(y_value)
        values.append(row_values)

    if not values:
        raise ValueError("Table header found, but no numeric table rows were parsed")

    return GridTable(
        x_bins=x_bins,
        y_bins=y_bins,
        values=values,
        x_label=x_label,
        y_label=y_label,
        source=source_name,
    )


def format_table(table: GridTable, *, decimals: int = 2, delimiter: str = ",") -> str:
    """Format a grid table as delimited text, CSV by default."""

    label = f"{table.y_label}/{table.x_label}"
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
    writer.writerow([label, *(_format_axis(value) for value in table.x_bins)])
    for y_value, row in zip(table.y_bins, table.values):
        formatted_values = [_format_value(value, decimals=decimals) for value in row]
        writer.writerow([_format_axis(y_value), *formatted_values])
    return output.getvalue()


def cell_weights(
    x_bins: list[float],
    y_bins: list[float],
    x: float,
    y: float,
    *,
    out_of_bounds: OutOfBoundsMode = "skip",
    mode: Literal["bilinear", "nearest"] = "bilinear",
) -> list[tuple[int, int, float]]:
    """Return `(row_index, col_index, weight)` cells affected by a sample."""

    if mode == "nearest":
        x_index = nearest_axis_index(x_bins, x, out_of_bounds=out_of_bounds)
        y_index = nearest_axis_index(y_bins, y, out_of_bounds=out_of_bounds)
        if x_index is None or y_index is None:
            return []
        return [(y_index, x_index, 1.0)]

    x_bracket = axis_bracket(x_bins, x, out_of_bounds=out_of_bounds)
    y_bracket = axis_bracket(y_bins, y, out_of_bounds=out_of_bounds)
    if x_bracket is None or y_bracket is None:
        return []

    x0, x1, tx = x_bracket
    y0, y1, ty = y_bracket
    x_weights = [(x0, 1.0)] if x0 == x1 else [(x0, 1.0 - tx), (x1, tx)]
    y_weights = [(y0, 1.0)] if y0 == y1 else [(y0, 1.0 - ty), (y1, ty)]

    result: list[tuple[int, int, float]] = []
    for row, y_weight in y_weights:
        for col, x_weight in x_weights:
            weight = y_weight * x_weight
            if weight > 0:
                result.append((row, col, weight))
    return result


def axis_bracket(
    bins: list[float],
    value: float,
    *,
    out_of_bounds: OutOfBoundsMode = "skip",
) -> tuple[int, int, float] | None:
    if not bins:
        return None
    if len(bins) == 1:
        if out_of_bounds == "clamp" or math.isclose(value, bins[0]):
            return (0, 0, 0.0)
        return None

    ordered = sorted(enumerate(bins), key=lambda item: item[1])
    min_index, min_value = ordered[0]
    max_index, max_value = ordered[-1]
    if value < min_value:
        return (min_index, min_index, 0.0) if out_of_bounds == "clamp" else None
    if value > max_value:
        return (max_index, max_index, 0.0) if out_of_bounds == "clamp" else None

    for index, axis_value in ordered:
        if math.isclose(value, axis_value):
            return (index, index, 0.0)

    for (lower_index, lower_value), (upper_index, upper_value) in zip(ordered, ordered[1:]):
        if lower_value <= value <= upper_value:
            span = upper_value - lower_value
            t = 0.0 if span == 0 else (value - lower_value) / span
            return (lower_index, upper_index, t)
    return None


def nearest_axis_index(
    bins: list[float],
    value: float,
    *,
    out_of_bounds: OutOfBoundsMode = "skip",
) -> int | None:
    bracket = axis_bracket(bins, value, out_of_bounds=out_of_bounds)
    if bracket is None:
        return None
    first, second, t = bracket
    if first == second:
        return first
    return first if t < 0.5 else second


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text()


def _looks_like_path(value: str) -> bool:
    if "\n" in value or "\t" in value:
        return False
    suffix = Path(value).suffix.lower()
    return suffix in {".csv", ".tsv", ".txt", ".ve", ".afr"} and Path(value).exists()


def _tokenize(line: str) -> list[str]:
    stripped = line.strip()
    if "\t" in stripped:
        return [token.strip() for token in next(csv.reader([stripped], delimiter="\t"))]
    if "," in stripped:
        return [token.strip() for token in next(csv.reader([stripped]))]
    return [token.strip() for token in re.split(r"\s+", stripped) if token.strip()]


def _find_table_header(rows: list[list[str]]) -> int | None:
    for index, tokens in enumerate(rows):
        start = _x_start(tokens)
        if start is None:
            continue
        numeric = [_parse_float(token) is not None for token in tokens[start:]]
        if len(numeric) >= 2 and all(numeric):
            following = rows[index + 1 : index + 5]
            if any(_looks_like_table_row(row, len(tokens) - start) for row in following):
                return index
    return None


def _x_start(tokens: list[str]) -> int | None:
    if len(tokens) < 2:
        return None
    if _parse_float(tokens[0]) is None and all(_parse_float(token) is not None for token in tokens[1:]):
        return 1
    if all(_parse_float(token) is not None for token in tokens):
        return 0
    return None


def _looks_like_table_row(tokens: list[str], expected_values: int) -> bool:
    if len(tokens) < expected_values + 1:
        return False
    if _parse_float(tokens[0]) is None:
        return False
    return all(_parse_float(token) is not None for token in tokens[1 : expected_values + 1])


def _split_axis_label(label: str) -> tuple[str, str]:
    cleaned = label.strip() or "MAP/RPM"
    for separator in ("/", "\\"):
        if separator in cleaned:
            left, right = cleaned.split(separator, 1)
            return left.strip() or "MAP", right.strip() or "RPM"
    lowered = cleaned.lower()
    if "rpm" in lowered:
        return "MAP", cleaned
    return cleaned, "RPM"


def _parse_float(token: str) -> float | None:
    cleaned = token.strip().strip('"').replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _require_float(token: str, description: str) -> float:
    value = _parse_float(token)
    if value is None:
        raise ValueError(f"Invalid {description}: {token!r}")
    return value


def _lerp(start: float, end: float, t: float) -> float:
    return start + (end - start) * t


def _format_axis(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def _format_value(value: float, *, decimals: int) -> str:
    text = f"{value:.{decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text
