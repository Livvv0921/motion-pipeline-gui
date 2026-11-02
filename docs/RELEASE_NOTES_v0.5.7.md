# Motion Pipeline GUI v0.5.7

v0.5.7 is the final pre-GitHub workflow/UI release and introduces real concurrent backend execution.

## Highlights

- Run independent Passive Reading, Calibration, Triangulation, and Visualization jobs concurrently.
- See overall progress above the console and per-stage progress in the sidebar.
- Restore movable/floating console docking with quick Dock Right / Dock Bottom controls.
- Fully collapse Compare Lab controls and let plots use the freed space.
- Open Peak Lab and Movement Lab sections expanded by default.
- Standardize plotting colors to Coral Grove, Orchid Dusk, and Aqua Current.
- Use a `#212226` dark canvas and clean white light canvas.

## Safety note

Parallel jobs share CPU, RAM, disk/network bandwidth, and GPU/VRAM. Do not run jobs that write to the same output paths concurrently.

## Validation

Source files were statically parsed/compiled during release preparation. Full visual/Qt regression testing should be completed on the lab workstation using `docs/TESTING.md`.
