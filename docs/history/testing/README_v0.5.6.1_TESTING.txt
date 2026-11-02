Motion Pipeline GUI v0.5.6.1 — regression testing
=================================================

Launch
------
Windows:
  conda activate motion-gui
  cd <motion_pipeline_gui_v0.5.6.1>
  python launcher.py

This release is primarily a UI/bug-fix patch. Existing v0.5.6 data files and Peak Lab session files remain conceptually compatible; new Peak Lab sessions identify themselves as v0.5.6.1.

A. Theme test
-------------
1. Toggle Light mode.
2. Expected UI family: warm blush / pink surfaces, burgundy text, purple + teal accents.
3. Open Movement Lab with X/Y/Z visible.
4. Confirm traces have strong contrast in Light mode.
5. Toggle Dark mode and confirm Movement Lab changes to brighter traces.

B. Peak Lab layout test
-----------------------
1. Load a 3D CSV and enable X/Y/Z.
2. Choose Primary trace on top.
3. Expected: ONE shared coordinate canvas. This should resemble the original Peak Lab overlay behavior.
4. The selected Primary axis should be visually strongest and should render above the other traces.
5. Choose Separate XYZ.
6. Expected: only this mode creates three individual plot rows.
7. Zoom into a movement, select/move/remove a peak, and verify the prior v0.5.6 zoom-preservation behavior still works.

C. Peak Lab full-width / vertical resize
----------------------------------------
1. Press HIDE CONTROLS.
2. Confirm the left Peak Lab tool column disappears completely.
3. Confirm Plotly expands horizontally.
4. Drag the EVENT DATASET splitter to give the plot more vertical space.
5. Expected: the graph grows with the Qt viewport; no large unused blank region remains below it.
6. Press SHOW CONTROLS to restore the tools.

D. Compare Lab full-width / stacked resize
------------------------------------------
1. Add 2–4 traces.
2. Choose Stacked subplots.
3. Hide controls.
4. Confirm the plot uses the full width.
5. Drag/collapse the TRACE SET lower splitter area.
6. Confirm the graph fills the available vertical space rather than keeping a fixed-height Plotly canvas.
7. Repeat for Compact stacked and Overlay.
8. Verify PNG/SVG/PDF/HTML export still works as before.

E. Triangulation safeguards
---------------------------
1. With an existing raw 3D CSV/NPY and Overwrite existing 3D OFF, press Run.
2. Expected: GUI message explains that output already exists and triangulation is skipped BEFORE backend launch.
3. With overwrite ON, normal triangulation should still launch.
4. Test READ TOML / Auto camera count on the lab calibration.toml.
5. Expected: common Aniposelib list, mapping, and camera-table layouts are accepted. Manual camera count remains the fallback.

F. Movement Lab exact-match safety
----------------------------------
1. Load a 3D CSV under a recording folder containing a YYYYMMDD_HHMMSS token.
2. Expected auto-selected raw folder must contain exactly the same timestamp token.
3. A nearby recording with a different timestamp must not be silently chosen.
4. Test video seek, -5 s, +5 s, playback speed, and trace cursor synchronization.

Known test limitation of the build environment
----------------------------------------------
The release source is syntax/compile checked here, but the final visual Qt behavior must be click-tested on a machine with PySide6/QtWebEngine installed (your normal GUI environment).
