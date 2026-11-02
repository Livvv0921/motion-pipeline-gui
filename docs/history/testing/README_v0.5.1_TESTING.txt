Motion Pipeline GUI v0.5.1 — Compare Lab focused test

Launch exactly as before from the motion-gui environment.

Recommended test:
1. Open Visualization > Compare Lab.
2. Select a CSV such as:
   .../Passive_20260731_111816/3d/raw_left_hand_right_hand_3d.csv
3. Press READ SOURCE.
   Expected Trace label: 20260731_111816.
4. Choose Left_Hand + x and add the trace.
5. Repeat for 2–4 recordings from other dates.
6. Try Plot mode = Overlay.
7. Try Plot mode = Stacked vertically.
   - One trace should appear per row.
   - Rows share the X axis.
   - Rows use the same numeric Y range for direct consistency comparison.
8. Change Y-axis label and press UPDATE COMPARISON.
9. Uncheck Show trace labels / legend and update again.
10. Export the current visible view as PNG.

This patch does not change Peak Lab or any processing backend.
