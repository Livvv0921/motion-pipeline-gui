Motion Pipeline GUI v0.5.6 — focused testing checklist
======================================================

Launch
------
conda activate motion-gui
cd <your extracted motion_pipeline_gui_v0.5.6 folder>
python launcher.py

The build container used to prepare v0.5.6 did not include PySide6, so every Python file was syntax/compile checked but the Qt GUI itself must be click-tested on your normal GUI machine.

1) Triangulation trial-folder guard
-----------------------------------
A. Open 03 / TRIANGULATION.
B. Confirm the hint explicitly says NOT to select trial_folder/3d.
C. Select an actual .../trial_folder/3d directory as Trial folder and press RUN TRIANGULATION.
Expected: a warning tells you to select the parent trial folder instead.
D. Select the correct parent folder containing camera H5 files.
Expected: validation proceeds normally.

2) Triangulation threshold step
-------------------------------
Click the Score threshold arrows repeatedly.
Expected: 0.5 -> 0.6 -> 0.7 etc., and downward 0.5 -> 0.4 -> 0.3.
Also type a value such as 0.35 manually.
Expected: manual decimal values remain accepted.

3) Movable console / triangulation layout
-----------------------------------------
A. Keep the console docked at the bottom.
B. Drag its title bar/edge upward and downward.
Expected: the triangulation page resizes; the hint and RUN TRIANGULATION controls should not paint behind the console.
C. Dock the console left/right and float it.
Expected: movable-console behavior from v0.5.5 remains available.

4) Light theme + palettes
-------------------------
A. Switch to Light mode.
Expected: main background is #DCD6E2 and primary interaction accents use #443959 / #1D7B80.
B. Open Peak Lab and Compare Lab.
Expected: both offer the same palette names:
- Classic — Blue / Coral / Pink
- Plum — Lavender / Teal
- Electric — Blue / Lime / Brown
- Neon — Violet / Cyan / Blue
- Forest — Mint / Slate / Olive
C. In Light mode choose Plum — Lavender / Teal.
Expected: all three traces remain visible; the lavender trace should not disappear into the background.

5) Peak Lab trace layouts
-------------------------
A. Load a 3D CSV with X/Y/Z data.
B. Keep X, Y, Z visible and try all three Trace layout options.
Expected:
- Overlay: X/Y/Z share one y-axis.
- Separate XYZ: each visible coordinate has its own vertically stacked row.
- Primary trace on top: the selected Primary axis appears first and receives more vertical space; the other visible axes remain below it.
C. Change Primary axis from Z to X/Y.
Expected: Primary trace on top reorders accordingly.

6) Peak Lab zoom persistence
----------------------------
A. Zoom tightly around one movement.
B. Select an event row in EVENT DATASET.
Expected: the plot does NOT zoom back out.
C. Move a selected peak using MANUAL REVIEW > Frame > MOVE SELECTED PEAK.
Expected: the event moves and the same zoom window is retained.
D. Remove a selected peak.
Expected: the same zoom window is retained.
E. Run FIND PEAKS in the current working range.
Expected: redraw keeps the zoom when compatible with the active range.
F. Press FULL RANGE.
Expected: this intentionally clears the remembered zoom and shows the full recording.

7) Manual Review move/remove controls
-------------------------------------
A. Select exactly one event row.
Expected: its frame appears in MANUAL REVIEW > Frame.
B. Enter another frame and press MOVE SELECTED PEAK.
Expected: frame/time/XYZ/velocity_3d update together.
C. Select one or more event rows and press REMOVE SELECTED PEAK in MANUAL REVIEW.
Expected: this removes the same rows as EVENT DATASET > REMOVE SELECTED.
You should not need to drag the lower dataset panel larger just to remove an event.

8) Peak/timepoint velocity
--------------------------
A. Detect or manually add peaks, confirm them, and export CSV.
B. Inspect the output.
Expected: a velocity_3d column is present for each exported event/timepoint row.
Definition: magnitude of consecutive-frame XYZ displacement divided by elapsed time. Units follow the coordinate units per second.

9) Peak Lab save/reopen review session
--------------------------------------
A. Load data, choose a palette/layout, zoom, detect peaks, move/remove at least one event, and leave some work unfinished.
B. Press SAVE SESSION and write a JSON file.
C. Close/reopen the GUI or load another source, then OPEN SESSION.
Expected: source, signal controls, layout, palette, working range, saved zoom, and labeled events return.
D. Enable "Save review session with export" and export CSV or MAT.
Expected: scientific output is saved normally AND a separate <export_stem>_peak_session.json is written beside it.
The JSON is not embedded into the event dataset.

10) Movement Lab automatic video match
--------------------------------------
A. First use Triangulation with an exact Raw video folder.
B. Load the corresponding 3D CSV in Movement Lab (or use USE PEAK LAB SOURCE then LOAD CSV).
Expected: Raw videos is automatically populated when the recording ID/path can be matched.
C. Browse to a different folder manually.
Expected: manual override still works.

11) Movement Lab Video Inspector
--------------------------------
A. Open VIDEO INSPECTION and read the instruction text.
B. Open Video Inspector.
C. Drag the seek slider.
Expected: video seeks and the plot cursor follows.
D. Press -5 s and +5 s.
Expected: both video and plot cursor jump accordingly.
E. Try 0.5x, 1.0x, 1.5x, and 2.0x playback.
Expected: cursor pace follows playback.
F. Before video playback/seek begins, inspect the movement plot.
Expected: no phantom dashed video cursor is shown.
G. During playback, watch the cursor.
Expected: it should advance stably using the closest CSV time_seconds frame and should not rapidly spike between duplicate positions.

12) Compare Lab layouts / palette / export
------------------------------------------
A. Add 2–4 traces.
B. Confirm plot modes include Overlay, Stacked subplots, and Compact stacked (no "Anipose-style" wording).
C. Try the shared palette options.
D. In Export format, test:
- PNG
- SVG
- PDF
- Interactive HTML
Expected: HTML exports without kaleido. PNG/SVG/PDF export when kaleido is installed.

13) Context/status sanity check
-------------------------------
In Peak Lab confirm the compact status line updates with:
- source CSV filename
- selected bodypart
- primary axis
- confirmed/total review count

14) Regression smoke test
-------------------------
Confirm the following v0.5.5 behavior still works:
- Passive Reading launches backend processing.
- Calibration settings and camera count remain usable.
- Triangulation raw/filtered versions still run.
- Peak Lab short-gap fill, Savitzky-Golay, Butterworth, manual add, undo, confirm, CSV and MAT export still work.
- Movement Lab movement-window dataset CSV/MAT export still works.
- Compare Lab trace add/remove/clear and Frame / Elapsed time / Relative frame x-axis modes still work.
- Console can still dock bottom/left/right or float.
- NEW DRAFT preserves intended environment/theme/protocol defaults.
