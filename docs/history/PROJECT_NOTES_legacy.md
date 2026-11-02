# Motion Pipeline GUI — current baseline: v0.5.6

v0.5.5 keeps the classic v0.5.2/v0.5.4 visual layout. Peak Lab remains Plotly-based; no Matplotlib toolbar/editor redesign is used.

## Core pipeline
Raw videos → DLC 2D predictions → optional named filter variants → calibration → 3D triangulation + timestamps → Visualization / Peak Lab / Movement Lab / Compare Lab.

## Environment architecture
The GUI is intentionally lightweight and launches backend scripts through user-selected Python executables. DeepLabCut and Aniposelib can remain in separate environments.

- Windows: the child-process runner retains environment/DLL isolation for selected Conda Python executables.
- macOS/Linux: select `<environment>/bin/python`; Windows DLL logic is skipped.

## v0.5.5 Peak Lab review model
- `event_index` is chronological within event label + bodypart + primary axis.
- The visible Event Dataset is sorted chronologically within those groups.
- Automatic detections are drafts until confirmed; use `✓ CONFIRM KEPT` for a whole-table confirmation or `✓ CONFIRM RANGE + CONTINUE` for the range workflow.
- Manual additions are intentional user annotations and are confirmed immediately.
- Reject false peaks by unchecking `keep`.
- Reposition a peak with table row → Manual Review Frame → MOVE SELECTED PEAK.
- Primary axis `None` is view-only; choose X/Y/Z to detect/add an axis-specific event.

## Filters
Passive Reading can create separate 2D prediction variants:
- median (DLC-native)
- arima (DLC-native)
- savgol (Savitzky–Golay x/y smoothing)
- butterworth (zero-phase Butterworth low-pass x/y smoothing; source-video FPS when available)

All filters are OFF by default. Triangulation can convert any available variant into a separately named 3D CSV, which makes direct filter comparisons in Compare Lab possible without changing Compare Lab's data model.

Peak Lab's Savitzky–Golay / Butterworth cleanup is a separate post-triangulation 3D visualization/detection option and does not overwrite the loaded CSV.

## Testing
Use `TEST_SHEET_v0.5.5.md` for exploratory/regression testing. macOS setup is in `MACOS_SETUP_v0.5.5.md`.

## v0.5.6 focus
v0.5.6 is a workflow/review usability release: safer triangulation folder selection, stable dock resizing, shared themes/palettes, Peak Lab layout/zoom/session/velocity improvements, synchronized Movement Lab video controls, and expanded Compare Lab export formats. See `README_v0.5.6_TESTING.txt` and `CHANGELOG_v0.5.6.txt`.
