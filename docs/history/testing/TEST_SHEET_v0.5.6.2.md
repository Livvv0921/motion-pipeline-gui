# Motion Pipeline GUI v0.5.6.2 — quick visual test

This patch only changes the light-mode visual system. Dark mode and analysis behavior should remain unchanged.

## 1. Light mode shell
- Switch to **Light mode**.
- Confirm the main window is a light warm cream/khaki, not pink.
- Confirm panels are slightly darker warm neutral shades.
- Confirm text is dark brown and easy to read.
- Confirm the UI does not feel dominated by bright yellow; yellow/olive should appear mainly in selected/focus states.

## 2. Buttons and controls
- Check Passive Reading, Calibration, Triangulation, Visualization, Peak Lab, Movement Lab and Compare Lab.
- Primary/important buttons should have strong brown or muted-blue emphasis.
- Inputs should remain light and readable.
- Hover/focus/selected states should remain visibly distinct.

## 3. Plot readability
- Open Peak Lab in Light mode and load a normal 3D CSV.
- With the default/classic palette, confirm X/Y/Z traces are dark brown, olive and muted blue and are easy to distinguish.
- Confirm event/peak markers remain visible against the neutral plot canvas.
- Repeat in Movement Lab.
- Repeat in Compare Lab.

## 4. Dark-mode regression
- Switch back to **Dark mode**.
- Confirm dark mode looks the same as v0.5.6.1 and traces remain bright enough to read.

## 5. v0.5.6.1 regression smoke test
- Peak Lab: Primary trace on top stays in one shared plot.
- Peak Lab / Compare Lab: Hide Controls expands the plot with no blank lower region.
- Movement Lab: exact recording ID is used for automatic raw-video matching.
