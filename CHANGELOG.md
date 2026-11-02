# Changelog

All notable Motion Pipeline GUI changes are tracked here. Older detailed notes are preserved in `docs/history/releases/`.

## v0.5.7

### Added
- True parallel backend jobs using independent process/settings snapshots.
- Aggregate progress above the console and temporary per-stage sidebar progress bars.
- Tagged console output for concurrent jobs.
- `STOP ALL RUNNING` support for all active backend jobs.
- Explicit **Dock Right** and **Dock Bottom** console controls.

### Changed
- Console can dock left/right/bottom or float again.
- Compare Lab controls can collapse fully and the plot expands into the released space.
- Peak Lab and Movement Lab collapsible sections open expanded by default.
- Plot palettes are standardized to three sets:
  - **Coral Grove** — `#F14666 #EE8980 #FFCDAA #9CB998`
  - **Orchid Dusk** — `#313866 #50409A #964EC2 #FF7BBF`
  - **Aqua Current** — `#3E54D3 #4F80E2 #15CDCA #4FE0B6`
- Dark canvas uses `#212226`.
- Light canvas is white with restrained Coral Grove accents.

### Safety / behavior
- Parallel tasks still share CPU/RAM/disk/network/GPU resources.
- Do not run jobs that write to the same output files concurrently.
- Background job completion uses launch-time settings snapshots to avoid overwriting a different draft currently being edited.

### Deferred
- Calibration-camera inspection remains deferred by design.

## v0.5.6.3
- Improved light-theme contrast and blue accent visibility.
- Peak Lab Move Mode automatically enables hover details.
- Unified plot/table/manual-review selected-event state.
- Restored visibly enlarged selected-peak markers without resetting zoom.

## v0.5.6.1–v0.5.6.2
- Refined light/dark themes and theme-aware trace colors.
- Restored classic Peak Lab primary-trace layout.
- Improved collapsible plot/control regions.
- Fixed exact Movement Lab raw-video recording matching.
- Improved calibration-camera-count parsing and triangulation existing-output handling.

## v0.5.6
- Safer triangulation folder workflow and 0.1 threshold stepping.
- Movement Lab video synchronization/seek/speed controls.
- Peak Lab layout modes, review-session persistence, zoom preservation, and per-frame 3D velocity export.
- Expanded Compare Lab exports (PNG/SVG/PDF/HTML).

For full historical notes, see `docs/history/releases/`.
