"""Parsing for MegaSquirt/TunerStudio style data logs."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DataLog:
    columns: list[str]
    units: list[str]
    rows: list[dict[str, float | str]]
    source: str | None = None

    def numeric_rows(self) -> Iterable[dict[str, float | str]]:
        return iter(self.rows)


def parse_datalog(path_or_text: str | Path, *, source: str | None = None) -> DataLog:
    """Parse a MegaSquirt `.msl`-style log from a path or text."""

    if isinstance(path_or_text, Path) or _looks_like_path(str(path_or_text)):
        path = Path(path_or_text)
        text = _read_text(path)
        source_name = source or str(path)
    else:
        text = str(path_or_text)
        source_name = source

    lines = [line.rstrip("\r\n") for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Data log is empty")

    tokenized = [_tokenize(line) for line in lines]
    header_index = _find_header(tokenized)
    if header_index is None:
        raise ValueError("Could not find a data log header row")

    columns = [token.strip() for token in tokenized[header_index]]
    if not columns:
        raise ValueError("Data log header row has no columns")

    row_start = header_index + 1
    units: list[str] = []
    if row_start < len(tokenized) and not _looks_like_data_row(tokenized[row_start], len(columns)):
        units = _pad(tokenized[row_start], len(columns))
        row_start += 1
    else:
        units = [""] * len(columns)

    rows: list[dict[str, float | str]] = []
    for tokens in tokenized[row_start:]:
        if not _looks_like_data_row(tokens, len(columns)):
            continue
        padded = _pad(tokens, len(columns))
        row: dict[str, float | str] = {}
        for column, token in zip(columns, padded):
            row[column] = _to_number(token)
        rows.append(row)

    if not rows:
        raise ValueError("Data log contains a header but no data rows")

    return DataLog(columns=columns, units=units, rows=rows, source=source_name)


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
    return suffix in {".msl", ".csv", ".tsv", ".txt"} and Path(value).exists()


def _tokenize(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith('"') and stripped.endswith('"') and "\t" not in stripped:
        stripped = stripped[1:-1]
    if "\t" in stripped:
        return [token.strip() for token in next(csv.reader([stripped], delimiter="\t"))]
    if "," in stripped:
        return [token.strip() for token in next(csv.reader([stripped]))]
    return [token.strip() for token in re.split(r"\s+", stripped) if token.strip()]


def _find_header(rows: list[list[str]]) -> int | None:
    for index, tokens in enumerate(rows):
        lowered = {token.strip().lower() for token in tokens}
        if "time" in lowered and ("map" in lowered or "rpm" in lowered or "rpm/100" in lowered):
            return index

    for index, tokens in enumerate(rows):
        if len(tokens) >= 4 and not _looks_like_data_row(tokens, len(tokens)):
            following = rows[index + 1 : index + 4]
            if any(_looks_like_data_row(row, len(tokens)) for row in following):
                return index
    return None


def _looks_like_data_row(tokens: list[str], column_count: int) -> bool:
    if len(tokens) < min(3, column_count):
        return False
    values = [_parse_float(token) for token in tokens[:column_count]]
    numeric_count = sum(value is not None for value in values)
    return numeric_count >= max(2, min(column_count, 5) - 1)


def _pad(tokens: list[str], size: int) -> list[str]:
    if len(tokens) >= size:
        return tokens[:size]
    return tokens + [""] * (size - len(tokens))


def _to_number(token: str) -> float | str:
    value = _parse_float(token)
    return value if value is not None else token


def _parse_float(token: str) -> float | None:
    cleaned = token.strip().strip('"').replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None

