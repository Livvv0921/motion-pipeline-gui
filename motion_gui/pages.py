from __future__ import annotations

from pathlib import Path
import re
import tomllib

import pandas as pd

from PySide6.QtCore import QSettings, QUrl, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None

from .peak_lab import PeakLab, infer_bodyparts
from .movement_lab import MovementLab
from .compare_lab import CompareLab
from .widgets import PathRow


def camera_identifiers(count: int):
    return [[f"Cam-{i}", f"camera_{i}"] for i in range(count)]


def comma_list(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;\n]+", text) if item.strip()]


def camera_count_from_toml(path: Path) -> int:
    """Read camera count from common Aniposelib TOML layouts.

    Aniposelib versions/calibration writers may serialize cameras as an array
    of tables, a mapping keyed by camera name, or individual camera-like
    tables. Keep the GUI helper tolerant while the backend remains the final
    authority for loading calibration parameters.
    """
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    def camera_like(value) -> bool:
        if not isinstance(value, dict):
            return False
        keys = {str(k).lower() for k in value.keys()}
        calibration_keys = {"matrix", "distortions", "rotation", "translation", "size"}
        return len(keys & calibration_keys) >= 2

    for key in ("cameras", "camera"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return len(value)
        if isinstance(value, dict) and value:
            camera_entries = [v for v in value.values() if isinstance(v, dict)]
            if camera_entries and all(camera_like(v) for v in camera_entries):
                return len(camera_entries)

    # Fallback for files with top-level [Cam-0], [Cam-1], ... sections.
    top_level = [v for v in data.values() if camera_like(v)]
    if len(top_level) >= 2:
        return len(top_level)

    # Last fallback: recursively locate the largest group of camera-like tables.
    groups: list[int] = []
    def walk(value):
        if isinstance(value, dict):
            children = [v for v in value.values() if camera_like(v)]
            if len(children) >= 2:
                groups.append(len(children))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            if len(value) >= 2 and all(camera_like(v) for v in value):
                groups.append(len(value))
            for child in value:
                walk(child)
    walk(data)
    if groups:
        return max(groups)
    raise ValueError("Could not identify camera entries in the calibration TOML; use the manual camera count.")


class BasePage(QWidget):
    step_key = ""

    def __init__(self, main, title: str, subtitle: str):
        super().__init__()
        self.main = main
        self.settings: QSettings = main.settings
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(18, 14, 18, 14)
        self.layout_root.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("subtitle")
        subtitle_label.setWordWrap(True)
        self.layout_root.addWidget(title_label)
        self.layout_root.addWidget(subtitle_label)

    def remembered(self, key: str, default=""):
        """Read a saved GUI setting, falling back when the stored value is null."""
        value = self.settings.value(key, default)
        return default if value is None else value

    def remember(self, key: str, value):
        self.settings.setValue(key, value)

    def ask_run(self, title: str, text: str) -> bool:
        return QMessageBox.question(
            self, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ) == QMessageBox.StandardButton.Yes

    @staticmethod
    def emphasize_run_button(button: QPushButton):
        """Give run actions a consistent, easy-to-scan position and visual weight."""
        button.setObjectName("runButton")
        button.setMinimumWidth(230)
        button.setToolTip("Run this processing stage using the settings shown above.")

    @staticmethod
    def add_right_aligned_button(layout: QVBoxLayout, button: QPushButton):
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        layout.addLayout(row)


class PassivePage(BasePage):
    step_key = "passive"

    def __init__(self, main):
        super().__init__(main, "01 / PASSIVE READING", "Run an existing trained DeepLabCut model on selected passive recordings, with optional Median, ARIMA, Savitzky–Golay, and Butterworth filtering.")

        paths = QGroupBox("PATHS & MODEL")
        grid = QGridLayout(paths)
        self.python = PathRow("DLC environment Python", mode="file", filter_text="Python executable (python.exe python python3)")
        self.python.setText(str(self.remembered("env/dlc_python", "python")))
        self.config = PathRow("DeepLabCut config.yaml", mode="file", filter_text="YAML (*.yaml *.yml)")
        self.config.setText(str(self.remembered("passive/config", "")))
        self.video_root = PathRow("Raw passive video root", mode="folder")
        self.video_root.setText(str(self.remembered("passive/video_root", "")))
        self.process_root = PathRow("Processed output root", mode="folder")
        self.process_root.setText(str(self.remembered("passive/process_root", "")))
        self.folders = QLineEdit(str(self.remembered("passive/folders", ""))); self.folders.setPlaceholderText("Recording folder names separated by commas")
        self.pick_folder = QPushButton("PICK RECORDING")
        self.pick_folder.clicked.connect(self._pick_recording)
        grid.addWidget(QLabel("DLC Python"),0,0); grid.addWidget(self.python,0,1,1,3)
        grid.addWidget(QLabel("Model config"),1,0); grid.addWidget(self.config,1,1,1,3)
        grid.addWidget(QLabel("Raw video root"),2,0); grid.addWidget(self.video_root,2,1,1,3)
        grid.addWidget(QLabel("Processed root"),3,0); grid.addWidget(self.process_root,3,1,1,3)
        grid.addWidget(QLabel("Recording folders"),4,0); grid.addWidget(self.folders,4,1,1,2); grid.addWidget(self.pick_folder,4,3)
        self.layout_root.addWidget(paths)

        opts = QGroupBox("ANALYSIS OPTIONS")
        g = QGridLayout(opts)
        self.extension = QComboBox(); self.extension.addItems([".mp4", ".avi", ".mov"])
        self.extension.setCurrentText(str(self.remembered("passive/ext", ".mp4")))
        self.shuffle = QSpinBox(); self.shuffle.setRange(1,100); self.shuffle.setValue(int(self.remembered("passive/shuffle", 4)))
        self.reanalyze = QCheckBox("Reanalyze existing raw predictions")
        self.refilter = QCheckBox("Overwrite existing filtered outputs")
        self.apply_filters = QCheckBox("Apply filters"); self.apply_filters.setChecked(False)
        self.median = QCheckBox("Median"); self.median.setChecked(False)
        self.arima = QCheckBox("ARIMA"); self.arima.setChecked(False)
        self.savgol = QCheckBox("Savitzky–Golay"); self.savgol.setChecked(False)
        self.butterworth = QCheckBox("Butterworth low-pass"); self.butterworth.setChecked(False)
        self.median_window = QSpinBox(); self.median_window.setRange(1,999); self.median_window.setSingleStep(2); self.median_window.setValue(5)
        self.arima_p = QDoubleSpinBox(); self.arima_p.setDecimals(5); self.arima_p.setRange(0,1); self.arima_p.setValue(0.001)
        self.ar_degree = QSpinBox(); self.ar_degree.setRange(0,50); self.ar_degree.setValue(3)
        self.ma_degree = QSpinBox(); self.ma_degree.setRange(0,50); self.ma_degree.setValue(1)
        self.alpha = QDoubleSpinBox(); self.alpha.setDecimals(4); self.alpha.setRange(0,1); self.alpha.setValue(0.01)
        self.savgol_window = QSpinBox(); self.savgol_window.setRange(3,999); self.savgol_window.setSingleStep(2); self.savgol_window.setValue(11)
        self.savgol_poly = QSpinBox(); self.savgol_poly.setRange(1,20); self.savgol_poly.setValue(2)
        self.butter_cutoff = QDoubleSpinBox(); self.butter_cutoff.setDecimals(2); self.butter_cutoff.setRange(0.01,500); self.butter_cutoff.setValue(6.0); self.butter_cutoff.setSuffix(" Hz")
        self.butter_order = QSpinBox(); self.butter_order.setRange(1,10); self.butter_order.setValue(4)
        self.save_raw_csv = QCheckBox("Save raw CSV")
        self.save_filtered_csv = QCheckBox("Save filtered CSV")
        self.ask_before = QCheckBox("Ask before processing"); self.ask_before.setChecked(True)
        g.addWidget(QLabel("Video type"),0,0); g.addWidget(self.extension,0,1)
        g.addWidget(QLabel("Shuffle"),0,2); g.addWidget(self.shuffle,0,3)
        g.addWidget(self.reanalyze,0,4); g.addWidget(self.ask_before,0,5)
        g.addWidget(self.apply_filters,1,0); g.addWidget(self.median,1,1); g.addWidget(self.arima,1,2); g.addWidget(self.savgol,1,3); g.addWidget(self.butterworth,1,4); g.addWidget(self.refilter,1,5)
        g.addWidget(QLabel("Median window"),2,0); g.addWidget(self.median_window,2,1)
        g.addWidget(QLabel("ARIMA p-bound"),2,2); g.addWidget(self.arima_p,2,3)
        g.addWidget(QLabel("AR degree"),2,4); g.addWidget(self.ar_degree,2,5)
        g.addWidget(QLabel("MA degree"),3,0); g.addWidget(self.ma_degree,3,1)
        g.addWidget(QLabel("Alpha"),3,2); g.addWidget(self.alpha,3,3)
        g.addWidget(QLabel("SavGol window"),4,0); g.addWidget(self.savgol_window,4,1)
        g.addWidget(QLabel("SavGol polyorder"),4,2); g.addWidget(self.savgol_poly,4,3)
        g.addWidget(QLabel("Butter cutoff"),5,0); g.addWidget(self.butter_cutoff,5,1)
        g.addWidget(QLabel("Butter order"),5,2); g.addWidget(self.butter_order,5,3)
        g.addWidget(self.save_raw_csv,5,4); g.addWidget(self.save_filtered_csv,5,5)
        self.layout_root.addWidget(opts)

        self.run_button = QPushButton("RUN PASSIVE ANALYSIS  →")
        self.emphasize_run_button(self.run_button)
        self.run_button.clicked.connect(self.run)
        self.layout_root.addStretch(1)
        self.add_right_aligned_button(self.layout_root, self.run_button)

    def _pick_recording(self):
        path = QFileDialog.getExistingDirectory(self, "Select one recording folder", self.video_root.text())
        if path:
            p = Path(path)
            self.video_root.setText(str(p.parent))
            names = comma_list(self.folders.text())
            if p.name not in names:
                names.append(p.name)
            self.folders.setText(", ".join(names))

    def run(self):
        if not Path(self.config.text()).is_file():
            QMessageBox.warning(self, "Model config", "Select an existing DeepLabCut config.yaml file."); return
        if not Path(self.video_root.text()).is_dir():
            QMessageBox.warning(self, "Raw video root", "Select an existing raw passive-video root folder."); return
        if not self.process_root.text():
            QMessageBox.warning(self, "Processed root", "Choose where DeepLabCut outputs should be written."); return
        filters = []
        if self.median.isChecked(): filters.append("median")
        if self.arima.isChecked(): filters.append("arima")
        if self.savgol.isChecked(): filters.append("savgol")
        if self.butterworth.isChecked(): filters.append("butterworth")
        if self.apply_filters.isChecked() and not filters:
            QMessageBox.warning(self, "Choose a filter", "Apply filters is enabled but no filter is selected.")
            return
        folders = comma_list(self.folders.text())
        if not folders:
            QMessageBox.warning(self, "No recordings", "Enter or pick at least one recording folder.")
            return
        if self.median.isChecked() and self.median_window.value() % 2 == 0:
            QMessageBox.warning(self, "Median window", "Median window length must be an odd positive integer.")
            return
        if self.savgol.isChecked() and (self.savgol_window.value() % 2 == 0 or self.savgol_poly.value() >= self.savgol_window.value()):
            QMessageBox.warning(self, "Savitzky–Golay", "SavGol window must be odd and larger than the polynomial order.")
            return
        if self.ask_before.isChecked() and not self.ask_run("Start passive analysis?", f"Analyze {len(folders)} recording folder(s) with the selected DLC model?"):
            return
        for key, value in {
            "env/dlc_python": self.python.text(), "passive/config": self.config.text(), "passive/video_root": self.video_root.text(),
            "passive/process_root": self.process_root.text(), "passive/folders": self.folders.text(), "passive/ext": self.extension.currentText(),
            "passive/shuffle": self.shuffle.value(),
        }.items(): self.remember(key, value)
        settings = {
            "CONFIG_PATH": self.config.text(), "VIDEO_ROOT": self.video_root.text(), "PROCESS_ROOT": self.process_root.text(),
            "FOLDERS_TO_ANALYZE": folders, "SHUFFLE": self.shuffle.value(), "VIDEO_EXTENSION": self.extension.currentText(),
            "REANALYZE_EXISTING": self.reanalyze.isChecked(), "APPLY_FILTERS": self.apply_filters.isChecked(),
            "FILTER_TYPES": filters, "REFILTER_EXISTING": self.refilter.isChecked(), "MEDIAN_WINDOW_LENGTH": self.median_window.value(),
            "ARIMA_P_BOUND": self.arima_p.value(), "ARIMA_AR_DEGREE": self.ar_degree.value(), "ARIMA_MA_DEGREE": self.ma_degree.value(),
            "ARIMA_ALPHA": self.alpha.value(), "SAVGOL_WINDOW_LENGTH": self.savgol_window.value(), "SAVGOL_POLYORDER": self.savgol_poly.value(),
            "BUTTERWORTH_CUTOFF_HZ": self.butter_cutoff.value(), "BUTTERWORTH_ORDER": self.butter_order.value(),
            "SAVE_RAW_AS_CSV": self.save_raw_csv.isChecked(), "SAVE_FILTERED_AS_CSV": self.save_filtered_csv.isChecked(),
        }
        self.main.run_backend("passive", self.python.text(), "passive_reading.py", settings)


class CalibrationPage(BasePage):
    step_key = "calibration"

    def __init__(self, main):
        super().__init__(main, "02 / CALIBRATION", "Create an Aniposelib camera calibration from one calibration recording. Your lab ChArUco dimensions are prefilled but still editable.")
        paths = QGroupBox("CALIBRATION INPUT / OUTPUT")
        g = QGridLayout(paths)
        self.python = PathRow("Aniposelib environment Python", mode="file")
        self.python.setText(str(self.remembered("env/anipose_python", "python")))
        self.video_folder = PathRow("Calibration recording folder", mode="folder")
        self.video_folder.setText(str(self.remembered("cal/video_folder", "")))
        self.output_root = PathRow("Processed calibration output root", mode="folder")
        self.output_root.setText(str(self.remembered("cal/output_root", "")))
        self.extension = QComboBox(); self.extension.addItems([".mp4", ".avi", ".mov"])
        self.camera_count = QSpinBox(); self.camera_count.setRange(2,32); self.camera_count.setValue(int(self.remembered("camera/count", 4)))
        g.addWidget(QLabel("Anipose Python"),0,0); g.addWidget(self.python,0,1,1,3)
        g.addWidget(QLabel("Calibration video folder"),1,0); g.addWidget(self.video_folder,1,1,1,3)
        g.addWidget(QLabel("Processed output root"),2,0); g.addWidget(self.output_root,2,1,1,3)
        g.addWidget(QLabel("Video type"),3,0); g.addWidget(self.extension,3,1)
        g.addWidget(QLabel("Camera count"),3,2); g.addWidget(self.camera_count,3,3)
        self.layout_root.addWidget(paths)

        board = QGroupBox("ChArUco BOARD")
        b = QGridLayout(board)
        self.columns = QSpinBox(); self.columns.setRange(2,100); self.columns.setValue(10)
        self.rows = QSpinBox(); self.rows.setRange(2,100); self.rows.setValue(8)
        self.square = QDoubleSpinBox(); self.square.setRange(0.001,10000); self.square.setDecimals(3); self.square.setValue(25.0)
        self.marker = QDoubleSpinBox(); self.marker.setRange(0.001,10000); self.marker.setDecimals(3); self.marker.setValue(18.75)
        self.bits = QSpinBox(); self.bits.setRange(3,7); self.bits.setValue(4)
        self.dictionary = QSpinBox(); self.dictionary.setRange(1,10000); self.dictionary.setValue(50)
        self.fisheye = QCheckBox("FISHEYE"); self.fisheye.setChecked(True)
        self.recalibrate = QCheckBox("RECALIBRATE / overwrite existing")
        self.ask_before = QCheckBox("Ask before calibration"); self.ask_before.setChecked(True)
        for i,(label,w) in enumerate([("Columns",self.columns),("Rows",self.rows),("Square length",self.square),("Marker length",self.marker),("Marker bits",self.bits),("Dictionary size",self.dictionary)]):
            b.addWidget(QLabel(label), i//3, (i%3)*2); b.addWidget(w, i//3, (i%3)*2+1)
        b.addWidget(self.fisheye,2,0); b.addWidget(self.recalibrate,2,2,1,2); b.addWidget(self.ask_before,2,4,1,2)
        self.layout_root.addWidget(board)

        hint = QLabel("Camera identifiers are generated from the camera count as Cam-0/camera_0, Cam-1/camera_1, ... in calibration order. This matches your existing scripts while keeping the number of cameras editable.")
        hint.setWordWrap(True); hint.setObjectName("hintLabel")
        self.layout_root.addWidget(hint)
        self.run_button = QPushButton("RUN CALIBRATION  →"); self.emphasize_run_button(self.run_button); self.run_button.clicked.connect(self.run)
        self.layout_root.addStretch(1); self.add_right_aligned_button(self.layout_root, self.run_button)

    def run(self):
        if not Path(self.video_folder.text()).is_dir():
            QMessageBox.warning(self, "Calibration folder", "Select an existing calibration video folder."); return
        if not self.output_root.text():
            QMessageBox.warning(self, "Calibration output", "Choose a processed calibration output root."); return
        if self.marker.value() >= self.square.value():
            QMessageBox.warning(self, "Board dimensions", "Marker length must be smaller than square length.")
            return
        if self.ask_before.isChecked() and not self.ask_run("Start calibration?", "Validation will run first. Continue into ChArUco detection and camera optimization if validation passes?"):
            return
        for k,v in {"env/anipose_python":self.python.text(),"cal/video_folder":self.video_folder.text(),"cal/output_root":self.output_root.text(),"camera/count":self.camera_count.value()}.items(): self.remember(k,v)
        ids = camera_identifiers(self.camera_count.value())
        settings = {
            "CALIBRATION_VIDEO_FOLDER": self.video_folder.text(), "CALIBRATION_OUTPUT_ROOT": self.output_root.text(),
            "VIDEO_EXTENSION": self.extension.currentText(), "CAMERA_IDENTIFIERS": ids,
            "CALIBRATION_CAMERA_NAMES": [f"Cam-{i}" for i in range(self.camera_count.value())],
            "CHARUCO_COLUMNS": self.columns.value(), "CHARUCO_ROWS": self.rows.value(), "SQUARE_LENGTH": self.square.value(),
            "MARKER_LENGTH": self.marker.value(), "MARKER_BITS": self.bits.value(), "DICTIONARY_SIZE": self.dictionary.value(),
            "FISHEYE": self.fisheye.isChecked(), "RECALIBRATE_EXISTING": self.recalibrate.isChecked(), "ASK_BEFORE_CALIBRATION": False,
        }
        self.main.run_backend("calibration", self.python.text(), "calibration.py", settings)


class TriangulationPage(BasePage):
    step_key = "triangulation"

    def __init__(self, main):
        super().__init__(main, "03 / TRIANGULATION + TIMESTAMPS", "Triangulate raw/filtered DLC H5 predictions into 3D data. Timestamp metadata is derived from the original videos and is enabled by default for later electrophysiology alignment.")

        p = QGroupBox("TRIAL PATHS")
        g = QGridLayout(p)
        self.python = PathRow("Aniposelib environment Python", mode="file"); self.python.setText(str(self.remembered("env/anipose_python", "python")))
        self.trial = PathRow("Processed trial folder containing H5 files", mode="folder"); self.trial.setText(str(self.remembered("tri/trial", "")))
        self.calibration = PathRow("calibration.toml", mode="file", filter_text="TOML (*.toml)"); self.calibration.setText(str(self.remembered("tri/calibration", "")))

        # v0.4: exact raw recording folder is now the primary timestamp source.
        # This is clearer than asking the user to supply a parent root and rely on
        # automatic trial-name matching.
        self.raw_folder = PathRow("Exact raw recording folder containing Cam-0... videos", mode="folder")
        self.raw_folder.setText(str(self.remembered("tri/raw_folder", "")))
        self.raw_root = PathRow("Optional parent raw-video root (advanced fallback)", mode="folder")
        self.raw_root.setText(str(self.remembered("tri/raw_root", "")))

        g.addWidget(QLabel("Anipose Python"),0,0); g.addWidget(self.python,0,1,1,3)
        g.addWidget(QLabel("Trial folder"),1,0); g.addWidget(self.trial,1,1,1,3)
        g.addWidget(QLabel("Calibration TOML"),2,0); g.addWidget(self.calibration,2,1,1,3)
        g.addWidget(QLabel("Raw video folder"),3,0); g.addWidget(self.raw_folder,3,1,1,3)
        g.addWidget(QLabel("Advanced raw root"),4,0); g.addWidget(self.raw_root,4,1,1,3)
        self.layout_root.addWidget(p)

        opts = QGroupBox("3D SETTINGS")
        o = QGridLayout(opts)
        self.raw = QCheckBox("raw"); self.raw.setChecked(True)
        self.median = QCheckBox("median"); self.median.setChecked(False)
        self.arima = QCheckBox("arima"); self.arima.setChecked(False)
        self.savgol = QCheckBox("savgol"); self.savgol.setChecked(False)
        self.butterworth = QCheckBox("butterworth"); self.butterworth.setChecked(False)
        self.bodyparts = QLineEdit(str(self.remembered("bodyparts", "Left_Hand, Right_Hand")))
        self.detect_bodyparts = QPushButton("DETECT FROM H5"); self.detect_bodyparts.clicked.connect(self._detect_bodyparts)
        self.camera_count = QSpinBox(); self.camera_count.setRange(2,32); self.camera_count.setValue(int(self.remembered("camera/count", 4)))
        self.auto_camera_count = QCheckBox("Auto camera count from calibration.toml"); self.auto_camera_count.setChecked(True)
        self.read_camera_count = QPushButton("READ TOML"); self.read_camera_count.clicked.connect(self._read_camera_count)
        self.threshold = QDoubleSpinBox(); self.threshold.setRange(0,1); self.threshold.setDecimals(2); self.threshold.setSingleStep(0.1); self.threshold.setValue(0.5)
        self.chunk = QSpinBox(); self.chunk.setRange(1,100000); self.chunk.setValue(500)
        self.fast = QCheckBox("Fast OpenCV triangulation"); self.fast.setChecked(True)
        self.undistort = QCheckBox("Undistort points"); self.undistort.setChecked(True)
        self.timestamps = QCheckBox("Attach frame/time/timestamp metadata"); self.timestamps.setChecked(True); self.timestamps.setEnabled(False)
        self.overwrite = QCheckBox("Overwrite existing 3D")
        self.checkpoint = QCheckBox("Checkpoint every chunk"); self.checkpoint.setChecked(True)
        self.ask_before = QCheckBox("Ask before triangulation"); self.ask_before.setChecked(True)
        versions = QWidget(); vl=QHBoxLayout(versions); vl.setContentsMargins(0,0,0,0); vl.addWidget(self.raw);vl.addWidget(self.median);vl.addWidget(self.arima);vl.addWidget(self.savgol);vl.addWidget(self.butterworth);vl.addStretch(1)
        o.addWidget(QLabel("Data versions"),0,0); o.addWidget(versions,0,1,1,3)
        o.addWidget(QLabel("Bodyparts"),1,0); o.addWidget(self.bodyparts,1,1,1,2); o.addWidget(self.detect_bodyparts,1,3)
        o.addWidget(QLabel("Camera count"),2,0); o.addWidget(self.camera_count,2,1)
        o.addWidget(self.auto_camera_count,2,2); o.addWidget(self.read_camera_count,2,3)
        o.addWidget(QLabel("Score threshold"),3,0); o.addWidget(self.threshold,3,1)
        o.addWidget(QLabel("Chunk size"),4,0); o.addWidget(self.chunk,4,1)
        o.addWidget(self.fast,4,2); o.addWidget(self.undistort,4,3)
        o.addWidget(self.timestamps,5,0,1,2); o.addWidget(self.overwrite,5,2); o.addWidget(self.checkpoint,5,3)
        o.addWidget(self.ask_before,6,0,1,2)

        # Let smaller screens expose every 3D option without crushing widgets.
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setMinimumHeight(150)
        settings_scroll.setMaximumHeight(320)
        settings_scroll.setWidget(opts)
        self.layout_root.addWidget(settings_scroll)

        note = QLabel("Trial folder reminder: select the processed recording folder that CONTAINS the camera H5 files — do not select its 3d subfolder. The GUI writes 3D outputs into trial_folder/3d automatically. Timestamp attachment is locked ON; select the exact raw recording folder whenever possible.")
        note.setWordWrap(True); note.setObjectName("hintLabel"); self.layout_root.addWidget(note)
        self.run_button = QPushButton("RUN TRIANGULATION  →"); self.emphasize_run_button(self.run_button); self.run_button.clicked.connect(self.run)
        self.layout_root.addStretch(1); self.add_right_aligned_button(self.layout_root, self.run_button)

    def _read_camera_count(self):
        try:
            path = Path(self.calibration.text())
            count = camera_count_from_toml(path)
            self.camera_count.setValue(count)
            self.remember("camera/count", count)
            self.main.append_console(f"Calibration TOML reports {count} camera(s).")
        except Exception as exc:
            QMessageBox.warning(self, "Could not read camera count", f"{exc}\n\nThe manual camera count will remain available as a fallback.")

    def _detect_bodyparts(self):
        folder = Path(self.trial.text())
        try:
            h5_files = sorted(folder.glob("*.h5"))
            if not h5_files: raise FileNotFoundError("No H5 files found in the trial folder.")
            df = pd.read_hdf(h5_files[0])
            if not isinstance(df.columns, pd.MultiIndex): raise ValueError("The H5 does not have DLC MultiIndex columns.")
            parts = sorted(set(str(x) for x in df.columns.get_level_values("bodyparts")))
            self.bodyparts.setText(", ".join(parts))
            self.remember("bodyparts", self.bodyparts.text())
        except Exception as exc: QMessageBox.critical(self,"Bodypart detection failed",str(exc))

    def run(self):
        if self.auto_camera_count.isChecked():
            try:
                self.camera_count.setValue(camera_count_from_toml(Path(self.calibration.text())))
            except Exception as exc:
                self.main.append_console(f"Auto camera count failed ({exc}); using manual value {self.camera_count.value()}.")
        trial_folder = Path(self.trial.text())
        if not trial_folder.is_dir():
            QMessageBox.warning(self, "Trial folder", "Select an existing processed trial folder containing DLC H5 files."); return
        if trial_folder.name.lower() == "3d":
            QMessageBox.warning(self, "Wrong trial folder", "You selected the 3d output subfolder. Choose its parent trial folder instead (the folder containing the camera H5 files). The GUI will use/create trial_folder/3d automatically."); return
        if not Path(self.calibration.text()).is_file():
            QMessageBox.warning(self, "Calibration TOML", "Select an existing calibration.toml file."); return
        if self.raw_folder.text():
            if not Path(self.raw_folder.text()).is_dir():
                QMessageBox.warning(self, "Raw video folder", "The exact raw recording folder does not exist."); return
        elif not Path(self.raw_root.text()).is_dir():
            QMessageBox.warning(self, "Raw video folder", "Select the exact raw recording folder containing the camera videos. The parent raw root is an advanced fallback only."); return
        versions=[v for v,c in (("raw",self.raw),("median",self.median),("arima",self.arima),("savgol",self.savgol),("butterworth",self.butterworth)) if c.isChecked()]
        parts=comma_list(self.bodyparts.text())
        if not versions or not parts:
            QMessageBox.warning(self,"Missing selection","Choose at least one data version and one bodypart."); return
        base = "_".join(re.sub(r"[^A-Za-z0-9]+","_",p).strip("_").lower() for p in parts) + "_3d"
        if not self.overwrite.isChecked():
            output_dir = trial_folder / "3d"
            existing = []
            for version in versions:
                for suffix in (".csv", ".npy"):
                    candidate = output_dir / f"{version}_{base}{suffix}"
                    if candidate.exists():
                        existing.append(candidate.name)
            if existing:
                shown = "\n".join(f"• {name}" for name in existing[:8])
                QMessageBox.information(
                    self,
                    "3D output already exists",
                    "Triangulation was not started because existing 3D output is being protected.\n\n"
                    f"{shown}\n\nEnable 'Overwrite existing 3D' only if you want to regenerate these files."
                )
                self.main.append_console("Triangulation skipped: 3D output already exists and overwrite is OFF.")
                return
        if self.ask_before.isChecked() and not self.ask_run("Start triangulation?", f"Triangulate {', '.join(versions)} for bodyparts {', '.join(parts)}?"): return
        for k,v in {
            "env/anipose_python":self.python.text(),"tri/trial":self.trial.text(),"tri/calibration":self.calibration.text(),
            "tri/raw_root":self.raw_root.text(),"tri/raw_folder":self.raw_folder.text(),"bodyparts":self.bodyparts.text(),"camera/count":self.camera_count.value()
        }.items(): self.remember(k,v)
        settings={
            "TRIAL_FOLDER":self.trial.text(),"CALIBRATION_PATH":self.calibration.text(),"DATA_VERSIONS":versions,"BODY_PARTS":parts,
            "CAMERA_IDENTIFIERS":camera_identifiers(self.camera_count.value()),"SCORE_THRESHOLD":self.threshold.value(),"CHUNK_SIZE":self.chunk.value(),
            "USE_FAST_TRIANGULATION":self.fast.isChecked(),"UNDISTORT_POINTS":self.undistort.isChecked(),"ASK_BEFORE_TRIANGULATION":False,
            "OVERWRITE_EXISTING_3D":self.overwrite.isChecked(),"SAVE_CHECKPOINT_AFTER_EACH_CHUNK":self.checkpoint.isChecked(),
            "OUTPUT_BASENAME":base,"RAW_VIDEO_ROOT":self.raw_root.text(),"RAW_VIDEO_FOLDER":self.raw_folder.text() or None,
        }
        self.main.last_output_basename = base
        self.main.run_backend("triangulation",self.python.text(),"triangulation_with_timestamps.py",settings)


class VisualizationPage(BasePage):
    step_key = "visualization"

    def __init__(self, main):
        super().__init__(main, "04 / VISUALIZATION + LABS", "Generate static/interactive plots, review peak events, label movement windows, compare recordings/conditions, inspect synchronized raw video, and export analysis datasets.")
        tabs = QTabWidget()
        plots = QWidget(); layout=QVBoxLayout(plots); layout.setContentsMargins(8,8,8,8)
        paths=QGroupBox("PLOT SOURCE")
        g=QGridLayout(paths)
        self.python=PathRow("Aniposelib/plotting environment Python",mode="file"); self.python.setText(str(self.remembered("env/anipose_python", "python")))
        self.trial=PathRow("Processed trial folder",mode="folder"); self.trial.setText(str(self.remembered("tri/trial", "")))
        self.basename=QLineEdit(str(self.remembered("viz/basename", "left_hand_right_hand_3d")))
        self.bodyparts=QLineEdit(str(self.remembered("bodyparts", "Left_Hand, Right_Hand")))
        self.detect=QPushButton("DETECT FROM 3D CSV"); self.detect.clicked.connect(self._detect_from_csv)
        g.addWidget(QLabel("Python"),0,0); g.addWidget(self.python,0,1,1,3)
        g.addWidget(QLabel("Trial folder"),1,0); g.addWidget(self.trial,1,1,1,3)
        g.addWidget(QLabel("CSV basename"),2,0); g.addWidget(self.basename,2,1)
        g.addWidget(QLabel("Bodyparts"),2,2); g.addWidget(self.bodyparts,2,3)
        g.addWidget(self.detect,3,3)
        layout.addWidget(paths)

        opts=QGroupBox("OUTPUTS & FIGURES"); o=QGridLayout(opts)
        self.raw=QCheckBox("raw");self.raw.setChecked(True); self.median=QCheckBox("median");self.median.setChecked(False); self.arima=QCheckBox("arima");self.arima.setChecked(False); self.savgol=QCheckBox("savgol");self.savgol.setChecked(False); self.butterworth=QCheckBox("butterworth");self.butterworth.setChecked(False)
        self.png=QCheckBox("PNG");self.png.setChecked(True); self.html=QCheckBox("Plotly HTML");self.html.setChecked(True)
        self.axis_compare=QCheckBox("Axis comparisons");self.axis_compare.setChecked(True)
        self.single=QCheckBox("Single traces");self.single.setChecked(True)
        self.xyz=QCheckBox("XYZ combined");self.xyz.setChecked(True)
        self.traj=QCheckBox("3D trajectories");self.traj.setChecked(True)
        self.range_slider=QCheckBox("Plotly range slider");self.range_slider.setChecked(True)
        self.overwrite=QCheckBox("Overwrite figures");self.overwrite.setChecked(True)
        self.nth=QSpinBox();self.nth.setRange(1,10000);self.nth.setValue(1)
        self.dpi=QSpinBox();self.dpi.setRange(50,1200);self.dpi.setValue(200)
        self.xaxis=QComboBox();self.xaxis.addItems(["frame","time"])
        vs=QWidget();vsl=QHBoxLayout(vs);vsl.setContentsMargins(0,0,0,0); [vsl.addWidget(w) for w in (self.raw,self.median,self.arima,self.savgol,self.butterworth)];vsl.addStretch(1)
        outs=QWidget();ol=QHBoxLayout(outs);ol.setContentsMargins(0,0,0,0);ol.addWidget(self.png);ol.addWidget(self.html);ol.addStretch(1)
        o.addWidget(QLabel("Versions"),0,0);o.addWidget(vs,0,1,1,3);o.addWidget(QLabel("Output"),0,4);o.addWidget(outs,0,5)
        o.addWidget(self.axis_compare,1,0);o.addWidget(self.single,1,1);o.addWidget(self.xyz,1,2);o.addWidget(self.traj,1,3);o.addWidget(self.range_slider,1,4);o.addWidget(self.overwrite,1,5)
        o.addWidget(QLabel("Every Nth frame"),2,0);o.addWidget(self.nth,2,1);o.addWidget(QLabel("PNG DPI"),2,2);o.addWidget(self.dpi,2,3);o.addWidget(QLabel("X axis"),2,4);o.addWidget(self.xaxis,2,5)
        layout.addWidget(opts)
        self.run_button=QPushButton("GENERATE VISUALIZATIONS  →");self.emphasize_run_button(self.run_button);self.run_button.clicked.connect(self.run)
        layout.addStretch(1);self.add_right_aligned_button(layout, self.run_button)
        tabs.addTab(plots,"PLOTS")

        self.peak_lab=PeakLab(); self.peak_lab.message.connect(self.main.append_console)
        tabs.addTab(self.peak_lab,"PEAK LAB")

        self.movement_lab=MovementLab(self.peak_lab, self.settings)
        self.movement_lab.message.connect(self.main.append_console)
        self.peak_lab.sourceLoaded.connect(self.movement_lab.set_source_path)
        tabs.addTab(self.movement_lab,"MOVEMENT LAB")

        self.compare_lab=CompareLab()
        self.compare_lab.message.connect(self.main.append_console)
        tabs.addTab(self.compare_lab,"COMPARE LAB")

        viewer = QWidget(); viewer_layout = QVBoxLayout(viewer); viewer_layout.setContentsMargins(8,8,8,8)
        viewer_row = QHBoxLayout()
        self.html_path = PathRow("Open any generated Plotly HTML inside the GUI", mode="file", filter_text="HTML files (*.html)")
        self.open_html = QPushButton("OPEN INTERACTIVE HTML")
        self.open_html.clicked.connect(self._open_html_viewer)
        viewer_row.addWidget(self.html_path,1); viewer_row.addWidget(self.open_html)
        viewer_layout.addLayout(viewer_row)
        if QWebEngineView is not None:
            self.html_web = QWebEngineView(); viewer_layout.addWidget(self.html_web,1)
        else:
            self.html_web = None
            no_web = QLabel("QtWebEngine is unavailable. Install the full PySide6 package to embed Plotly HTML in the GUI.")
            no_web.setWordWrap(True); viewer_layout.addWidget(no_web,1)
        tabs.addTab(viewer,"HTML VIEWER")

        self.layout_root.addWidget(tabs,1)
        self.tabs=tabs

    def _open_html_viewer(self):
        if self.html_web is None:
            QMessageBox.warning(self, "Viewer unavailable", "QtWebEngine is not available in this GUI environment.")
            return
        path = Path(self.html_path.text())
        if not path.is_file():
            QMessageBox.warning(self, "HTML not found", "Select an existing Plotly .html file.")
            return
        self.html_web.load(QUrl.fromLocalFile(str(path.resolve())))
        self.main.append_console(f"Opened interactive Plotly HTML in GUI -> {path}")

    def _detect_from_csv(self):
        folder=Path(self.trial.text())/"3d"
        try:
            files=sorted(folder.glob("*.csv"))
            if not files: raise FileNotFoundError("No 3D CSV files found.")
            df=pd.read_csv(files[0],nrows=5)
            parts=infer_bodyparts(df.columns)
            if not parts: raise ValueError("Could not infer bodyparts from _x/_y/_z columns.")
            self.bodyparts.setText(", ".join(parts))
            name=files[0].stem
            for prefix in ("raw_","median_","arima_","savgol_","butterworth_"):
                if name.startswith(prefix): name=name[len(prefix):];break
            self.basename.setText(name)
            self.remember("bodyparts",self.bodyparts.text()); self.remember("viz/basename",name)
        except Exception as exc: QMessageBox.critical(self,"Detection failed",str(exc))

    def run(self):
        if not Path(self.trial.text()).is_dir():
            QMessageBox.warning(self, "Trial folder", "Select an existing processed trial folder."); return
        if not self.basename.text().strip():
            QMessageBox.warning(self, "CSV basename", "Enter or detect the triangulation CSV basename."); return
        versions=[v for v,c in (("raw",self.raw),("median",self.median),("arima",self.arima),("savgol",self.savgol),("butterworth",self.butterworth)) if c.isChecked()]
        parts=comma_list(self.bodyparts.text())
        if not versions or not parts: QMessageBox.warning(self,"Missing selection","Choose at least one version and one bodypart.");return
        self.remember("env/anipose_python",self.python.text());self.remember("tri/trial",self.trial.text());self.remember("bodyparts",self.bodyparts.text());self.remember("viz/basename",self.basename.text())
        singles=[f"{bp}_{axis}" for bp in parts for axis in ("x","y","z")]
        settings={
            "TRIAL_FOLDER":self.trial.text(),"CSV_BASENAME":self.basename.text(),"VERSIONS_TO_PLOT":versions,"BODY_PARTS":parts,
            "CREATE_MATPLOTLIB_PNG":self.png.isChecked(),"CREATE_PLOTLY_HTML":self.html.isChecked(),"CREATE_AXIS_COMPARISON_PLOTS":self.axis_compare.isChecked(),
            "CREATE_SINGLE_TRACE_PLOTS":self.single.isChecked(),"SINGLE_TRACE_COLUMNS":singles,"CREATE_XYZ_COMBINED_PLOTS":self.xyz.isChecked(),
            "CREATE_3D_TRAJECTORY_PLOTS":self.traj.isChecked(),"PLOT_EVERY_NTH_FRAME":self.nth.value(),"FIGURE_DPI":self.dpi.value(),
            "OVERWRITE_EXISTING_FIGURES":self.overwrite.isChecked(),"PLOTLY_SHOW_RANGE_SLIDER":self.range_slider.isChecked(),"X_AXIS_MODE":self.xaxis.currentText(),
        }
        self.main.run_backend("visualization",self.python.text(),"visualization_with_timestamps.py",settings)
