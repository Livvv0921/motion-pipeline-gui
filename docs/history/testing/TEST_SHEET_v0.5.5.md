# Motion Pipeline GUI v0.5.5 — Exploratory Test Sheet

Use this as a repeatable checklist after future updates. Mark each item **PASS / FAIL / NOT TESTED** and add notes/screenshots when something looks wrong.

## A. Launch / layout / global controls

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| A1 | Launch with `python launcher.py` / `run_gui.bat` | Main window opens without traceback | |
| A2 | Toggle dark/light theme | All pages remain readable; Plotly redraws in current theme | |
| A3 | Hide/show sidebar | Active page expands/contracts cleanly | |
| A4 | Open Console | Console docks at bottom and shows status/progress area | |
| A5 | Drag bottom Console upward | Console can reach approximately half the GUI height; page above remains usable | |
| A6 | Drag Console to left/right and float it | Docking/floating works without covering controls | |
| A7 | Open Quick Help | Current-page help tab is selected and searchable | |

## B. Passive Reading

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| B1 | Open Passive Reading fresh | **Apply filters, Median, ARIMA, Savitzky–Golay, Butterworth are all unchecked** | |
| B2 | Run raw only | Raw DLC H5 is created/reused; no filtered H5 is requested | |
| B3 | Median only | `*_median.h5` is created/reused | |
| B4 | ARIMA only | `*_arima.h5` is created/reused | |
| B5 | Savitzky–Golay only | `*_savgol.h5` is created/reused; likelihood column is preserved | |
| B6 | Butterworth only | `*_butterworth.h5` is created/reused; source video FPS is used when available | |
| B7 | Multiple filters together | Separate H5 variants coexist; raw H5 remains unchanged | |
| B8 | Invalid SavGol settings | GUI blocks even window or polyorder >= window with a clear warning | |
| B9 | Re-run with overwrite OFF | Existing selected filtered outputs are reused | |
| B10 | Re-run with overwrite ON | Selected filtered outputs are recreated | |

### Filter comparison note
The Savitzky–Golay and Butterworth options in Passive Reading operate on **2D DLC x/y coordinates before triangulation**. Peak Lab's cleanup filters operate on the **loaded 3D coordinate after triangulation**. They answer slightly different QC questions, so keep the stage/filter in your graph labels.

## C. Calibration

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| C1 | Select calibration folder and Python | Paths remain visible and editable | |
| C2 | Run known-good calibration | `calibration.toml` and log are produced | |
| C3 | Missing camera/file | GUI/backend gives readable error instead of silently continuing | |

## D. Triangulation

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| D1 | Open Triangulation fresh | Raw selected; median/arima/savgol/butterworth unchecked | |
| D2 | Triangulate raw | `raw_<basename>.csv/.npy` created | |
| D3 | Triangulate each filtered version | Corresponding `median_`, `arima_`, `savgol_`, `butterworth_` 3D CSVs are created | |
| D4 | Select a version whose H5 does not exist | Backend reports exactly which version/camera is missing and continues other selected versions | |
| D5 | Timestamp check | CSV contains `frame`, `time_seconds`, `timestamp`, and bodypart XYZ columns | |

## E. Visualization / Plot outputs

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| E1 | DETECT FROM 3D CSV on any version | Bodyparts and basename are inferred; version prefix is removed correctly | |
| E2 | Generate raw plot | PNG/HTML options work as selected | |
| E3 | Generate savgol/butterworth plot | New version prefixes are recognized | |

## F. Peak Lab — load / view

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| F1 | LOAD CSV | Valid 3D CSV loads and graph appears | |
| F2 | Change Bodypart | Graph updates without clearing event dataset | |
| F3 | Set Primary axis = X/Y/Z | Chosen axis is emphasized and FIND PEAKS uses it | |
| F4 | Set Primary axis = None | Visible traces remain viewable; no single detection axis is emphasized | |
| F5 | FIND PEAKS while Primary axis=None | Clear message asks you to choose X/Y/Z; no crash | |
| F6 | Toggle X/Y/Z visibility | Trace visibility changes independently | |
| F7 | Toggle Hover details | Hover details turn on/off | |

## G. Peak Lab — cleanup / detection

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| G1 | Savitzky–Golay cleanup | Cleaned trace appears; raw reference can be shown | |
| G2 | Butterworth cleanup | Low-pass trace appears; timing remains aligned | |
| G3 | Fill short gaps | Only bounded gaps <= selected frame count are filled | |
| G4 | Select working range and FIND PEAKS | Draft events are generated only inside range | |
| G5 | Re-run same/overlapping range | Overlapping draft auto-peaks are replaced rather than appended as duplicate batches | |

## H. Peak Lab — event dataset / manual review

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| H1 | Inspect event table after FIND PEAKS | Rows are chronological within event label + bodypart + primary axis | |
| H2 | Inspect `event_index` | It reads 1,2,3... in chronological frame order for that signal | |
| H3 | Turn Hover details ON + use peak selection | Matching event row can be located/selected for review | |
| H4 | Uncheck `keep` on false peak | Peak is excluded from kept export; row remains available for review | |
| H5 | Select row → change Manual Review Frame → MOVE SELECTED PEAK | Event moves to nearest real frame; timestamp and XYZ update too | |
| H6 | ADD MANUAL FRAME | Diamond/manual event is inserted at chronological position rather than bottom | |
| H7 | Manual event confirmation | Newly added manual event counts as confirmed immediately | |
| H8 | Click `✓ CONFIRM KEPT` | All checked draft rows become confirmed and exportable | |
| H9 | Confirm current range | Current draft range becomes confirmed and full range returns | |
| H10 | EXPORT KEPT CSV | Only checked + confirmed rows export | |
| H11 | EXPORT KEPT MAT | Same kept/confirmed event set exports to MAT | |

## I. Movement Lab

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| I1 | Peak Lab source loads | Movement Lab receives source path | |
| I2 | Select movement window | Start/end and duration update | |
| I3 | Add movement window | One movement row is created with expected label/set number | |
| I4 | Open video inspector | Correct cameras can be selected and graph cursor tracks frame | |
| I5 | Export movement data | CSV/MAT exports succeed | |

## J. Compare Lab

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| J1 | READ SOURCE | CSV loads; bodypart/frame range populate | |
| J2 | Add multiple filter CSVs | Raw/median/arima/savgol/butterworth can coexist as independent traces | |
| J3 | Overlay | All traces share one plot | |
| J4 | Stacked subplots | One trace per row; common value scale preserved | |
| J5 | Compact stacked | Compact Anipose-style view renders | |
| J6 | Drag vertical divider left/right | Left controls resize to a safe minimum and are never clipped underneath the plot | |
| J7 | Set Graph title = `Kimchi filter comparison` → Plotly camera icon | Suggested downloaded filename uses `Kimchi_filter_comparison` | |
| J8 | EXPORT FULL FIGURE PNG | Save dialog default filename is based on Graph title, not `tracking_comparison` | |

## K. macOS smoke test

| ID | Test | Expected result | Status / notes |
|---|---|---|---|
| K1 | Run `setup_macos.command` | `.venv` installs GUI dependencies | |
| K2 | Run `run_gui.command` | GUI launches | |
| K3 | Select DLC environment `.../bin/python` | Passive backend launches from that environment | |
| K4 | Select Aniposelib `.../bin/python` | Calibration/Triangulation backend launches from that environment | |
| K5 | Plotly/QtWebEngine | Peak Lab and Compare Lab embedded plots render | |
| K6 | Network/mounted data path | BROWSE-selected macOS path works without Windows drive-letter assumptions | |

## Regression rule for future versions
Before calling a new version stable, rerun at minimum: **A1, A5, B2, D2, F1, H1, H4, H6, H8, J6, J8** plus one real end-to-end trial.
