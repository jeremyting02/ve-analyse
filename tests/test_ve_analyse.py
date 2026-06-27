import unittest

from ve_analyse.analyzer import AnalyzerConfig, analyze
from ve_analyse.datalog import parse_datalog
from ve_analyse.graph import build_plot_series, detect_time_column, numeric_columns
from ve_analyse.table import format_table, parse_table


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


if __name__ == "__main__":
    unittest.main()
