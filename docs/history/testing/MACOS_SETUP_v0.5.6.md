# Motion Pipeline GUI v0.5.6 — macOS setup

The v0.5.6 codebase is cross-platform. Windows keeps `run_gui.bat`; macOS adds `setup_macos.command` and `run_gui.command`.

## First-time GUI setup on macOS

Recommended: keep the lightweight GUI environment separate from DeepLabCut and Aniposelib, exactly like on Windows.

### Easiest Finder workflow
1. Extract the v0.5.6 folder somewhere writable.
2. Control-click `setup_macos.command` → **Open** the first time if Gatekeeper asks.
3. The script creates a local `.venv` and installs `requirements-gui.txt`.
4. After setup completes, double-click `run_gui.command`.

### Terminal equivalent
```bash
cd /path/to/motion_pipeline_gui_v0.5.6
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-gui.txt
python launcher.py
```

## Backend Python paths on macOS

The GUI can still launch DeepLabCut and Aniposelib from separate environments. In each page, select the actual environment Python executable.

Common Conda/Miniforge examples:
```text
/Users/YOUR_NAME/miniforge3/envs/DEEPLABCUT/bin/python
/Users/YOUR_NAME/miniforge3/envs/anipose-jax/bin/python
```

To find the exact path:
```bash
conda activate DEEPLABCUT
python -c "import sys; print(sys.executable)"
```

Repeat for the Aniposelib environment.

## macOS notes
- Windows drive letters such as `Z:\...` do not exist on macOS. Choose mounted/network folders through **BROWSE** instead.
- The Windows DLL-isolation code is automatically skipped on macOS.
- QtWebEngine, Plotly, Peak Lab, Movement Lab, and Compare Lab use the same source code on both platforms.
- Raw-video playback depends on codecs supported by Qt Multimedia on the Mac.
- If macOS blocks a `.command` file, Control-click it → **Open** once, or run `chmod +x run_gui.command setup_macos.command` in Terminal.
