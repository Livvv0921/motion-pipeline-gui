# Architecture

## Design goal

The GUI is a lightweight orchestration/review layer around existing scientific Python environments. Heavy dependencies remain in stage-specific backend environments.

## Runtime layers

### GUI process

`launcher.py` starts the PySide6 application in `motion_gui/`.

The GUI handles:
- path/settings forms
- theme and docking
- embedded Plotly review tools
- Peak Lab / Movement Lab / Compare Lab state
- concurrent job management
- console aggregation and progress display

### Backend job runner

`backend/step_runner.py` launches one backend script with a frozen JSON settings snapshot. On Windows it also prepares native DLL search paths for the selected environment.

### Backend scripts

- `backend/scripts/passive_reading.py`
- `backend/scripts/calibration.py`
- `backend/scripts/triangulation_with_timestamps.py`
- `backend/scripts/visualization_with_timestamps.py`

Each script can run with the Python executable selected for that stage.

## Parallel jobs

v0.5.7 uses independent child processes rather than a single global process. This allows, for example, triangulation for Trial A while visualizing Trial B.

The job manager stores per-job settings snapshots so completion callbacks do not use a different trial currently displayed in the GUI.

Parallelism does not remove hardware constraints. Avoid concurrent writes to the same files and monitor GPU memory when running multiple DLC jobs.

## Data flow

```text
raw synchronized videos
        |
        v
DeepLabCut 2D H5 predictions
        |
        +--> optional 2D filtered variants
        |
        v
Aniposelib camera calibration + triangulation
        |
        v
3D CSV/NPY + timing metadata
        |
        +--> Visualization
        +--> Peak Lab
        +--> Movement Lab
        +--> Compare Lab
```

## Four-camera assumption

The current lab workflow is built around four synchronized cameras. Camera count can be read from calibration metadata where possible or set manually in the GUI.
