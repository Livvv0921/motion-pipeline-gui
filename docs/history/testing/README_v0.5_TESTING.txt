Motion Pipeline GUI v0.5 — suggested testing order
==================================================

Launch
------
conda activate motion-gui
cd <your extracted motion_pipeline_gui_v0.5 folder>
python launcher.py

1) Peak Lab: short gaps
-----------------------
- Load a triangulated 3D CSV that contains visible NaN gaps.
- Open SIGNAL CLEANUP.
- Turn on Fill short internal gaps and leave Maximum gap = 5 frames.
- Keep Smoothing = None and press APPLY CLEANUP TO VIEW.
- Confirm that only short gaps connect; long gaps should remain disconnected.
- Toggle Show raw reference to compare the source with the display signal.

2) Peak Lab: Savitzky–Golay
---------------------------
- Select Savitzky–Golay.
- Start with window = 11 and polynomial order = 2.
- Press APPLY CLEANUP TO VIEW.
- Compare the cleaned line with the dotted raw reference.
- FIND PEAKS should use the cleaned signal.

3) Peak Lab: Butterworth
------------------------
- Select Butterworth low-pass.
- Start with cutoff = 6 Hz and order = 4 for ~60 fps data.
- Press APPLY CLEANUP TO VIEW.
- Confirm long NaN gaps remain disconnected.

4) Range-by-range peak workflow
-------------------------------
- Start from FULL RANGE.
- SELECT RANGE ON PLOT and drag across one movement section.
- FIND PEAKS.
- Uncheck/remove/move any incorrect candidates.
- Press CONFIRM RANGE + CONTINUE.
- The graph should return to the full recording and those confirmed peaks should remain visible.
- Select a second range and repeat.
- EXPORT KEPT CSV/MAT should export confirmed checked events only.

5) Hand move tool
-----------------
- Turn on ✋ SELECT / MOVE PEAK.
- Click a peak dot OR click near a peak on the active trace.
- The matching table row should become selected.
- Click the corrected frame on the trace.
- Frame/time/XYZ should update together.
- You should not need to drag a marker precisely.

6) Compare Lab
--------------
- Open Visualization > COMPARE LAB.
- Choose a 3D CSV and READ SOURCE.
- Enter a descriptive Trace label, choose bodypart + X/Y/Z, and ADD TRACE TO COMPARISON.
- Repeat with another date/condition/filter CSV.
- Try Frame, Elapsed time, and Relative frame x-axis modes.
- Try the three gradient palette options.
- Zoom/pan, then EXPORT CURRENT VIEW PNG.

Notes
-----
- Raw source CSV files are never overwritten by Peak Lab cleanup.
- Short-gap interpolation is deliberately conservative: only bounded gaps <= the selected frame limit are filled.
- Savitzky–Golay and Butterworth settings are starting points, not universal scientifically correct parameters.
- Direct marker dragging in embedded Plotly can differ across Qt/Plotly builds; v0.5's supported workflow is the two-click hand tool.
