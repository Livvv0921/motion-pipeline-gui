# Motion Pipeline GUI v0.5.6.1 — focused test sheet

## 1. Light / dark theme
- Switch to **Light** mode.
- Confirm the app uses the warm blush background/panels and dark burgundy text.
- Open Movement Lab and confirm X/Y/Z traces are visibly darker against the light plot.
- Switch to **Dark** mode and confirm Movement Lab traces become brighter.

## 2. Peak Lab — Primary trace on top
- Load a 3D CSV.
- Show X, Y, and Z.
- Select **Primary trace on top**.
- Confirm there is **one shared plot**, not three separate subplot boxes.
- Change Primary axis between X/Y/Z and confirm that trace is thicker/fully opaque and drawn visually above the others.
- Select **Separate XYZ** and confirm only this mode produces individual subplot rows.

## 3. Peak Lab — hide controls / fill space
- Press **HIDE CONTROLS** in the Peak Lab plot header.
- Confirm the entire left control panel disappears.
- Confirm the plot expands to use the newly available width.
- Drag the EVENT DATASET splitter downward/upward and confirm the Plotly graph grows to fill the available vertical space without a large blank strip at the bottom.
- Press **SHOW CONTROLS** and confirm the panel returns.

## 4. Compare Lab — hide controls / stacked plot
- Add at least 2 traces.
- Choose **Stacked subplots**.
- Press **HIDE CONTROLS**.
- Confirm the full left trace-selection panel disappears and the plot expands.
- Resize/drag the TRACE SET lower panel and confirm stacked plots fill the available vertical viewport instead of leaving empty space at the bottom.
- Repeat with **Compact stacked** and **Overlay**.

## 5. Triangulation existing-output safeguard
- Select a trial that already contains `3d/raw_<basename>.csv` or `.npy`.
- Leave **Overwrite existing 3D** OFF.
- Press Run.
- Expected: a clean **3D output already exists** message appears and the backend does not start.
- Turn overwrite ON only if you intentionally want to regenerate the files.

## 6. Calibration camera count
- Select your normal Aniposelib `calibration.toml`.
- Press **READ TOML** or leave auto camera count enabled.
- Confirm the expected camera count is detected. If not, manual count must still remain usable.

## 7. Movement Lab exact raw-video matching
- Load a CSV from a trial such as `Passive_YYYYMMDD_HHMMSS`.
- Confirm any automatically chosen raw-video folder contains the exact same `YYYYMMDD_HHMMSS` token.
- Confirm a different nearby recording timestamp is never selected automatically.
