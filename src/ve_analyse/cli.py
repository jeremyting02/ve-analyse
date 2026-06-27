"""Command-line interface for VE Analyse."""

from __future__ import annotations

import argparse
from pathlib import Path

from .analyzer import AnalyzerConfig, analyze
from .datalog import parse_datalog
from .table import format_table, parse_table


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logs = [parse_datalog(Path(path)) for path in args.log]
    ve_table = parse_table(Path(args.ve_table))
    afr_table = parse_table(Path(args.afr_table))
    config = AnalyzerConfig(
        rpm_column=args.rpm_col,
        map_column=args.map_col,
        o2_column=args.o2_col,
        o2_is_afr=args.o2_is_afr,
        wideband_afr_at_0v=args.afr_at_0v,
        wideband_afr_at_5v=args.afr_at_5v,
        min_rpm=args.min_rpm,
        min_clt=args.min_clt,
        max_clt=args.max_clt,
        min_pw=args.min_pw,
        max_tpsacc=args.max_tpsacc,
        min_gego=args.min_gego,
        max_gego=args.max_gego,
        out_of_bounds="clamp" if args.clamp else "skip",
        distribution="nearest" if args.nearest else "bilinear",
        weight_by_time=args.weight_by_time,
        max_time_weight=args.max_time_weight,
        min_samples_per_cell=args.min_samples,
        min_cell_weight=args.min_cell_weight,
        authority=args.authority,
        max_sample_correction=args.max_sample_correction,
        max_cell_change=args.max_cell_change,
        smoothing_passes=args.smoothing_passes,
        smoothing_factor=args.smoothing_factor,
        output_decimals=args.output_decimals,
    )

    result = analyze(logs, ve_table, afr_table, config)
    output_path = Path(args.output)
    output_path.write_text(format_table(result.table, decimals=args.output_decimals), encoding="utf-8")

    if args.summary_json:
        print(result.summary_json())
    else:
        print(result.summary_text())
        print(f"Wrote: {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MegaLogViewer-style VE table analyser")
    parser.add_argument("--log", action="append", required=True, help="Data log path. Repeat for multiple logs.")
    parser.add_argument("--ve-table", required=True, help="Current VE table path.")
    parser.add_argument("--afr-table", required=True, help="AFR target table path.")
    parser.add_argument("--output", required=True, help="Output VE table path.")

    columns = parser.add_argument_group("columns")
    columns.add_argument("--rpm-col", default=None, help="RPM column name. Defaults to RPM, then RPM/100.")
    columns.add_argument("--map-col", default=None, help="MAP/load column name. Defaults to MAP.")
    columns.add_argument("--o2-col", default=None, help="O2/AFR column name. Defaults to O2, then AFR.")

    wideband = parser.add_argument_group("wideband")
    wideband.add_argument("--o2-is-afr", action="store_true", help="Treat the O2 column as AFR instead of voltage.")
    wideband.add_argument("--afr-at-0v", type=float, default=10.0, help="AFR represented by 0 V wideband output.")
    wideband.add_argument("--afr-at-5v", type=float, default=20.0, help="AFR represented by 5 V wideband output.")

    filters = parser.add_argument_group("filters")
    filters.add_argument("--min-rpm", type=float, default=400.0)
    filters.add_argument("--min-clt", type=_optional_float, default=60.0, help="Minimum coolant temp, or 'none'.")
    filters.add_argument("--max-clt", type=_optional_float, default=None, help="Maximum coolant temp, or 'none'.")
    filters.add_argument("--min-pw", type=_optional_float, default=0.5, help="Minimum pulse width, or 'none'.")
    filters.add_argument("--max-tpsacc", type=_optional_float, default=110.0, help="Maximum TPSacc, or 'none'.")
    filters.add_argument("--min-gego", type=_optional_float, default=None, help="Minimum Gego/EGO correction, or 'none'.")
    filters.add_argument("--max-gego", type=_optional_float, default=None, help="Maximum Gego/EGO correction, or 'none'.")

    algorithm = parser.add_argument_group("algorithm")
    algorithm.add_argument("--nearest", action="store_true", help="Update nearest cell only instead of bilinear distribution.")
    algorithm.add_argument("--clamp", action="store_true", help="Clamp points outside table axes instead of skipping them.")
    algorithm.add_argument("--weight-by-time", action="store_true", help="Weight samples by elapsed log time.")
    algorithm.add_argument("--max-time-weight", type=float, default=0.5, help="Maximum seconds of weight per row.")
    algorithm.add_argument("--min-samples", type=int, default=3, help="Minimum samples required before changing a cell.")
    algorithm.add_argument("--min-cell-weight", type=float, default=0.0, help="Minimum weighted evidence before changing a cell.")
    algorithm.add_argument("--authority", type=float, default=1.0, help="Fraction of calculated correction to apply.")
    algorithm.add_argument("--max-sample-correction", type=float, default=0.25, help="Per-sample correction limit as a fraction.")
    algorithm.add_argument("--max-cell-change", type=float, default=0.15, help="Per-run cell change limit as a fraction.")
    algorithm.add_argument("--smoothing-passes", type=int, default=0)
    algorithm.add_argument("--smoothing-factor", type=float, default=0.20)
    algorithm.add_argument("--output-decimals", type=int, default=2)

    parser.add_argument("--summary-json", action="store_true", help="Print machine-readable summary JSON.")
    return parser


def _optional_float(value: str) -> float | None:
    if value.lower() in {"none", "null", "off"}:
        return None
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())

