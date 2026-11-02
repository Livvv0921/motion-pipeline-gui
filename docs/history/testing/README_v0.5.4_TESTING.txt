V0.5.4 QUICK TEST — CLASSIC PEAK LAB

This release intentionally restores the v0.5.2 Peak Lab look.
There should be NO Matplotlib toolbar and NO large Matplotlib navigation icons.

1. Launch the GUI using the clean environment that already launches the app.
   You do not need to reinstall requirements for this update.

2. Open Peak Lab and load the same triangulated 3D CSV you used in v0.5.2.
   Expected:
   - bodyparts populate
   - frame range populates
   - Plotly trace renders in the original style
   - data remains loaded even if a plot-render message occurs

3. Find peaks as usual.

4. RELIABLE MOVE TEST:
   a. Expand MANUAL REVIEW.
   b. Click exactly one event row in EVENT DATASET.
   c. The existing Frame box should change to that row's current frame.
   d. Type a different corrected frame into Frame.
   e. Press MOVE SELECTED PEAK.
   f. Expected: the event moves to the nearest real frame and frame/time/timestamp/XYZ all update.

5. OPTIONAL GRAPH ASSIST:
   - With one row selected, turn on the top-right hand button.
   - If a normal Plotly graph click is delivered, clicking the trace sets the Frame box to that destination.
   - Then press MOVE SELECTED PEAK to commit.
   - If graph clicks are not delivered on your machine, simply type the destination frame. The reliable path still works.

6. ADD MANUAL FRAME:
   - Type a missing event frame in Frame.
   - Press ADD MANUAL FRAME.
   - A manual event row/marker should be created using that frame's source time and XYZ coordinates.
