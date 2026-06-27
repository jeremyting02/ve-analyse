import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from ve_analyse.analyzer import AnalyzerConfig, analyze
from ve_analyse.datalog import parse_datalog
from ve_analyse.graph import build_plot_series, detect_time_column, numeric_columns
from ve_analyse.state import UiState, load_ui_state, save_ui_state
from ve_analyse.table import format_table, parse_table
from ve_analyse.webapi import analyse_payload, graph_payload, state_payload, table_payload


LOG_TEXT = """"MS/Extra format hr_11d  ********: MS/Extra hr_11d  ***************"
"Capture Date: Sat Jun 27 11:40:15 NZST 2026, File author: TunerStudio MS Lite! version 3.3.01"
Time	SecL	RPM/100	MAP	TP	O2	MAT	CLT	Engine	Gego	Gair	Gwarm	Gbaro	Gammae	TPSacc	Gve	PW	RPM
s	sec	r100						bits	%	%	%	%	%	%	%	s
0.000	152	10	40	10	2.500	-40.0	83.3	129	100	145	100	100	145	100	40	2.068	1000
0.081	152	10	40	10	2.500	-40.0	83.3	129	100	145	100	100	145	100	40	2.117	1000
0.162	152	10	40	10	2.500	-40.0	83.3	129	100	145	100	100	145	100	40	2.117	1000
"""


VE_TABLE = """MAP/RPM\t1000\t2000
40\t40\t50
60\t60\t70
"""


AFR_TABLE = """MAP/RPM\t1000\t2000
40\t14.7\t14.7
60\t14.0\t14.0
"""


class VeAnalyseTests(unittest.TestCase):
    def test_parse_datalog_megasquirt_format(self):
        log = parse_datalog(LOG_TEXT, source="inline")

        self.assertEqual(len(log.rows), 3)
        self.assertIn("RPM", log.columns)
        self.assertEqual(log.rows[0]["O2"], 2.5)

    def test_exact_cell_update_uses_measured_over_target_afr(self):
        log = parse_datalog(LOG_TEXT, source="inline")
        ve = parse_table(VE_TABLE, source="ve")
        afr = parse_table(AFR_TABLE, source="afr")

        result = analyze(
            [log],
            ve,
            afr,
            AnalyzerConfig(min_samples_per_cell=1, output_decimals=3),
        )

        self.assertEqual(result.accepted_rows, 3)
        self.assertEqual(result.table.values[0][0], 40.816)
        self.assertEqual(result.table.values[0][1], 50)
        self.assertEqual(result.table.values[1][0], 60)

    def test_bilinear_distribution_touches_surrounding_cells(self):
        log_text = LOG_TEXT.replace("\t40\t10\t2.500", "\t50\t10\t2.500").replace("\t1000", "\t1500")
        log = parse_datalog(log_text, source="inline")
        ve = parse_table(VE_TABLE, source="ve")
        afr = parse_table(AFR_TABLE, source="afr")

        result = analyze(
            [log],
            ve,
            afr,
            AnalyzerConfig(min_samples_per_cell=1, min_cell_weight=0.0),
        )

        self.assertEqual(len(result.updates), 4)
        self.assertTrue(all(update.weight > 0 for update in result.updates))

    def test_filters_skip_cold_rows(self):
        log = parse_datalog(LOG_TEXT.replace("\t83.3\t", "\t40.0\t"), source="inline")
        ve = parse_table(VE_TABLE, source="ve")
        afr = parse_table(AFR_TABLE, source="afr")

        result = analyze([log], ve, afr, AnalyzerConfig(min_clt=70, min_samples_per_cell=1))

        self.assertEqual(result.accepted_rows, 0)
        self.assertEqual(result.skip_reasons["below_min_clt"], 3)

    def test_time_weighting_advances_after_first_skipped_row(self):
        log = parse_datalog(LOG_TEXT, source="inline")
        ve = parse_table(VE_TABLE, source="ve")
        afr = parse_table(AFR_TABLE, source="afr")

        result = analyze(
            [log],
            ve,
            afr,
            AnalyzerConfig(weight_by_time=True, min_samples_per_cell=1),
        )

        self.assertEqual(result.accepted_rows, 2)
        self.assertEqual(result.skip_reasons["zero_weight"], 1)

    def test_format_table_outputs_comma_delimited_csv(self):
        ve = parse_table(VE_TABLE, source="ve")

        self.assertEqual(
            format_table(ve),
            "MAP/RPM,1000,2000\n40,40,50\n60,60,70\n",
        )

    def test_graph_helpers_find_numeric_columns_and_time_series(self):
        log = parse_datalog(LOG_TEXT, source="inline")

        self.assertEqual(detect_time_column(log), "Time")
        self.assertIn("O2", numeric_columns(log))

        series = build_plot_series(log, ["O2", "RPM"])

        self.assertEqual([item.name for item in series], ["O2", "RPM"])
        self.assertEqual(series[0].points[0], (0.0, 2.5))
        self.assertEqual(series[1].maximum, 1000.0)

    def test_ui_state_round_trips_json(self):
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state = UiState(
                log_paths=["run.msl"],
                ve_path="ve.csv",
                afr_path="afr.csv",
                output_path="new-ve.csv",
                parameters={"min_clt": "70"},
                graph_log="run.msl",
                graph_variables=["RPM", "MAP"],
                graph_groups=[{"id": "g1", "name": "Engine", "variables": ["RPM", "MAP"]}],
                active_graph_id="g1",
                graph_zoom={"x_min": 1.0, "x_max": 2.0},
                active_tab="Graph",
                geometry="900x700+1+2",
            )

            save_ui_state(state, state_path)
            loaded = load_ui_state(state_path)

            self.assertEqual(loaded.log_paths, ["run.msl"])
            self.assertEqual(loaded.parameters["min_clt"], "70")
            self.assertEqual(loaded.graph_variables, ["RPM", "MAP"])
            self.assertEqual(loaded.graph_groups[0]["name"], "Engine")
            self.assertEqual(loaded.active_graph_id, "g1")
            self.assertEqual(loaded.graph_zoom["x_max"], 2.0)
            self.assertEqual(loaded.active_tab, "Graph")

    def test_web_state_payload_adds_default_parameters(self):
        with TemporaryDirectory() as temp_dir:
            payload = state_payload(Path(temp_dir) / "missing-state.json")

            self.assertEqual(payload["parameters"]["min_clt"], "60")
            self.assertEqual(payload["parameters"]["distribution"], "bilinear")

    def test_web_graph_payload_builds_stacked_series_data(self):
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "run.msl"
            log_path.write_text(LOG_TEXT, encoding="utf-8")

            payload = graph_payload(str(log_path), ["O2", "RPM"], max_points_per_series=10)

            self.assertEqual(payload["row_count"], 3)
            self.assertEqual([item["name"] for item in payload["series"]], ["O2", "RPM"])
            self.assertEqual(payload["series"][0]["points"][0], (0.0, 2.5))

    def test_web_analyse_payload_writes_csv_output(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "run.msl"
            ve_path = root / "ve.tsv"
            afr_path = root / "afr.tsv"
            output_path = root / "ve-new.csv"
            log_path.write_text(LOG_TEXT, encoding="utf-8")
            ve_path.write_text(VE_TABLE, encoding="utf-8")
            afr_path.write_text(AFR_TABLE, encoding="utf-8")

            payload = analyse_payload(
                {
                    "log_paths": [str(log_path)],
                    "ve_path": str(ve_path),
                    "afr_path": str(afr_path),
                    "output_path": str(output_path),
                    "parameters": {"min_samples": "1"},
                }
            )

            self.assertTrue(output_path.exists())
            self.assertIn("MAP/RPM,1000,2000", output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["accepted_rows"], 3)
            self.assertEqual(payload["tables"]["old"]["x_bins"], [1000.0, 2000.0])
            self.assertEqual(payload["tables"]["old"]["y_bins"], [60.0, 40.0])
            self.assertEqual(payload["tables"]["old"]["values"][0], [60.0, 70.0])

    def test_web_table_payload_sorts_rpm_ascending_and_map_descending(self):
        table = parse_table(
            """MAP/RPM\t2000\t1000
40\t50\t40
60\t70\t60
""",
            source="inline",
        )

        payload = table_payload(table)

        self.assertEqual(payload["x_bins"], [1000.0, 2000.0])
        self.assertEqual(payload["y_bins"], [60.0, 40.0])
        self.assertEqual(payload["values"], [[60.0, 70.0], [40.0, 50.0]])


if __name__ == "__main__":
    unittest.main()
