# VE Analyse

VE Analyse is a small, dependency-free Python implementation of a MegaLogViewer HD-style VE analyser.

It takes:

- one or more MegaSquirt/TunerStudio data logs,
- a current VE table,
- an AFR target table,

and writes a revised VE table.

The first implementation supports tab/comma/whitespace delimited matrix tables where RPM bins are columns and load/MAP bins are rows:

```text
MAP/RPM  1000  2000  3000
40       42    45    49
60       55    59    64
```

Data logs use the common MegaSquirt `.msl`/MegaLogViewer text format. The default wideband conversion assumes the `O2` column is a linear voltage where `0 V = 10 AFR` and `5 V = 20 AFR`.

## Command line

```powershell
python -m ve_analyse --log path\to\run.msl --ve-table ve.tsv --afr-table afr.tsv --output ve-new.csv
```

Common tunables:

```powershell
python -m ve_analyse `
  --log run1.msl --log run2.msl `
  --ve-table ve.tsv `
  --afr-table afr.tsv `
  --output ve-new.csv `
  --min-clt 70 `
  --max-tpsacc 105 `
  --min-samples 3 `
  --authority 0.8 `
  --max-cell-change 0.12
```

See all parameters:

```powershell
python -m ve_analyse --help
```

Try the bundled mini example:

```powershell
python -m ve_analyse --log examples\example.msl --ve-table examples\ve.tsv --afr-table examples\afr.tsv --output examples\ve-new.csv --min-samples 1
```

## Simple UI

If Tkinter is available in your Python installation:

```powershell
python -m ve_analyse.gui
```

The UI has two tabs:

- `Analyse` writes a corrected VE table.
- `Graph` lets you load a data log, select any numeric variables, and view them over time.

The UI automatically restores its previous session, including opened log/table/output paths, parameter fields, selected graph log, selected graph variables, active tab, and window size. On Windows this is saved under `%APPDATA%\VE Analyse\state.json`.

The UI calls the same parser and analyser used by the CLI, so a web UI or richer desktop UI can be added later without duplicating the VE algorithm.

## Algorithm

For each accepted log row:

1. Detect/read RPM, MAP and O2.
2. Convert O2 voltage to measured AFR.
3. Interpolate the target AFR table at that RPM/MAP point.
4. Calculate the fuel correction as `measured AFR / target AFR`.
5. Apply the correction to the surrounding VE cells using bilinear weights.
6. Average corrections per cell, apply authority and change limits, and write the new VE value.

The main safety/tuning parameters are exposed in `ve_analyse.analyzer.AnalyzerConfig` and on the CLI.

This is not a byte-for-byte clone of MegaLogViewer HD. It is a practical VE analyser with explicit, inspectable behavior and tunable parameters.
