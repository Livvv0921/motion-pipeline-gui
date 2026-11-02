Motion Pipeline GUI v0.4 - suggested first test
================================================

1. Launch the GUI from the motion-gui Conda environment as before.
2. Keep Calibration/Triangulation backend Python set to the working aniposelib environment python.exe.
3. Peak Lab:
   - Load a 3D CSV.
   - Leave only Y visible and confirm Primary axis automatically becomes Y.
   - Zoom into a short movement and click USE CURRENT ZOOM.
   - Confirm Start/End and the range summary update.
   - Run FIND PEAKS; confirm only that working range is detected.
   - Click a peak dot, enable the hand tool, and click a corrected frame.
   - Test UNDO LAST and EXPORT KEPT MAT.
4. Movement Lab:
   - Click USE PEAK LAB SOURCE or load the same CSV.
   - Edit the movement protocol labels to match the lab's exact order and click REMEMBER DEFAULT.
   - Select a movement window and ADD MOVEMENT WINDOW + NEXT.
   - Confirm duration and reviewed peak count in the table.
   - Select the exact raw video recording folder, choose the camera count, and OPEN VIDEO INSPECTOR.
   - Play/seek the video and confirm the optional vertical cursor follows on the movement plot.
5. Console:
   - Drag the console title bar to the left/right/bottom or float it.
6. NEW DRAFT:
   - Use after testing to verify trial/file inputs are cleared while environment interpreters and remembered movement protocol remain.

Notes
-----
- The video cursor assumes raw video frame 0 corresponds to CSV frame 0/time 0, matching the current timestamp pipeline.
- Exact anatomical flexion/extension classification is not automated in v0.4. Generic signal extrema/phase order is available, but anatomical naming requires a validated landmark/coordinate rule (especially for shoulder motion).
- PySide6 was not installed in the build container, so Qt runtime behavior could not be launched here. All Python files were syntax/compile checked.
