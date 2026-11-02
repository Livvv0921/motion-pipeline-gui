# Installation

## Supported layout

Motion Pipeline GUI is designed around **three potentially separate Python environments**:

1. `motion-gui` — lightweight PySide6 desktop application
2. DeepLabCut backend — your lab-tested DLC/PyTorch environment
3. Aniposelib backend — calibration, triangulation, and visualization environment

This separation is intentional. Do not merge known-good backend environments just to run the GUI.

## GUI environment — Windows / Linux

Python 3.11+ is recommended.

```bash
conda create -n motion-gui python=3.11 -y
conda activate motion-gui
python -m pip install --upgrade pip
python -m pip install -r requirements-gui.txt
python launcher.py
```

After activating `motion-gui`, Windows users can also run `run_gui.bat`.

## GUI environment — macOS

### Automated local venv

From Finder/Terminal, run:

```bash
chmod +x setup_macos.command run_gui.command
./setup_macos.command
./run_gui.command
```

`setup_macos.command` creates `.venv` and installs `requirements-gui.txt`.

### Conda alternative

```bash
conda create -n motion-gui python=3.11 -y
conda activate motion-gui
python -m pip install -r requirements-gui.txt
python launcher.py
```

## DeepLabCut backend

For Passive Reading, select the Python executable from the DLC environment that already runs your trained model correctly.

Generic package families are listed in `requirements-backend-dlc.txt`, but DLC/PyTorch/CUDA combinations are version-sensitive. Prefer your lab's validated environment.

Typical executable locations:

```text
Windows: C:\Users\<user>\anaconda3\envs\<dlc-env>\python.exe
macOS/Linux: /.../envs/<dlc-env>/bin/python
```

## Aniposelib backend

For Calibration, Triangulation, and Visualization, select the Python executable from your working Aniposelib environment.

Charuco/Aruco workflows require an OpenCV build with the ArUco module. The generic requirements therefore use `opencv-contrib-python`.

Typical executable locations:

```text
Windows: C:\Users\<user>\anaconda3\envs\<anipose-env>\python.exe
macOS/Linux: /.../envs/<anipose-env>/bin/python
```

## Launching the GUI

```bash
python launcher.py
```

The GUI remembers selected environment executables and common paths through Qt settings on the local workstation.

## Troubleshooting

### Qt / PySide6 import failure

```bash
python -m pip install --upgrade PySide6
```

Make sure `python launcher.py` is being run from the GUI environment, not the DLC or Aniposelib backend environment.

### Windows native DLL issues

The backend runner explicitly adds common Conda native-library locations for the selected child Python environment. If a working notebook/environment succeeds but the GUI child process fails, capture the full console output and confirm the exact Python executable selected in the GUI.

### OpenCV ArUco / Charuco unavailable

Use an OpenCV contrib build in the Aniposelib environment:

```bash
python -m pip uninstall -y opencv-python opencv-python-headless
python -m pip install opencv-contrib-python
```

If your lab already has a working pinned OpenCV/NumPy combination, keep that combination rather than upgrading casually.

### Plot export

Static PNG/SVG/PDF export uses Plotly/Kaleido. Interactive HTML export does not require a browser connection.
