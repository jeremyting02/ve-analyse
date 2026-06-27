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
  --min-sample-authority 0.35 `
  --full-authority-samples 30 `
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

For the local web UI:

```powershell
python -m ve_analyse.webui
```

Then open:

```text
http://127.0.0.1:8765/
```

The web UI has:

- a session sidebar for log/table/output paths,
- browse buttons that open native file pickers for those paths,
- multiple graph tracks where each graph can contain its own selected variables,
- shared X-axis zooming with mouse wheel, drag-to-zoom, zoom-out, and reset controls,
- grouped analysis tunables,
- a results view showing the summary, old/new VE tables, delta map, and sample map,
- optional output path; if it is blank or not writable, the generated VE table can be downloaded from the Results view,
- automatic session restore using `.ve-analyse-web-state.json` in the directory where the server was launched.

If Tkinter is available in your Python installation:

```powershell
python -m ve_analyse.gui
```

The older Tkinter UI has two tabs:

- `Analyse` writes a corrected VE table.
- `Graph` lets you load a data log, select any numeric variables, and view them over time.

The Tkinter UI also restores its previous session. On Windows, the Tkinter state is saved under `%APPDATA%\VE Analyse\state.json`.

Both UIs call the same parser and analyser used by the CLI, so interface work stays separate from the VE algorithm.

## Portable Windows build

The app can be packaged as a portable Windows folder, with no installation required on the target machine. Build it on Windows with PyInstaller available:

```powershell
python -m pip install pyinstaller
.\scripts\build-portable-windows.ps1
```

The build creates:

```text
dist\VE-Analyse-Portable\
dist\VE-Analyse-Portable.zip
```

Users unzip the portable package and run:

```text
VE Analyse.exe
```

The launcher starts the local web UI, opens the default browser, and stores session state beside the executable in:

```text
data\state.json
```

Close the console window to stop the local web UI.

## Algorithm

For each accepted log row:

1. Detect/read RPM, MAP and O2.
2. Convert O2 voltage to measured AFR.
3. Interpolate the target AFR table at that RPM/MAP point.
4. Calculate the fuel correction as `measured AFR / target AFR`.
5. Apply the correction to the surrounding VE cells using bilinear weights.
6. Average corrections per cell.
7. Scale authority by per-cell sample confidence: cells at the minimum sample threshold use `min_sample_authority`, and cells at or above `full_authority_samples` use full configured authority.
8. Apply authority and change limits, then write the new VE value.

The main safety/tuning parameters are exposed in `ve_analyse.analyzer.AnalyzerConfig` and on the CLI.

This is not a byte-for-byte clone of MegaLogViewer HD. It is a practical VE analyser with explicit, inspectable behavior and tunable parameters.
