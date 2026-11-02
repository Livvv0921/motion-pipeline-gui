from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import tempfile
import uuid

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from scipy.io import savemat

from PySide6.QtCore import QObject, QUrl, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebChannel import QWebChannel

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None
    WEBENGINE_AVAILABLE = False

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except ImportError:
    QAudioOutput = QMediaPlayer = QVideoWidget = None
    MULTIMEDIA_AVAILABLE = False

from .theme import movement_trace_colors, plot_palette
from .widgets import PathRow


VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".m4v", ".wmv"}


def infer_bodyparts(columns) -> list[str]:
    axes: dict[str, set[str]] = {}
    for column in columns:
        match = re.match(r"^(.+)_([xyz])$", str(column))
        if match:
            axes.setdefault(match.group(1), set()).add(match.group(2))
    return sorted(name for name, found in axes.items() if {"x", "y", "z"}.issubset(found))


class MovementPlotBridge(QObject):
    selection = Signal(float, float)
    zoomRange = Signal(float, float)

    @Slot(str)
    def receiveSelection(self, payload: str):
        try:
            data = json.loads(payload)
            self.selection.emit(float(data["xmin"]), float(data["xmax"]))
        except Exception:
            pass

    @Slot(str)
    def receiveZoom(self, payload: str):
        try:
            data = json.loads(payload)
            self.zoomRange.emit(float(data["xmin"]), float(data["xmax"]))
        except Exception:
            pass


class CollapsiblePanel(QWidget):
    def __init__(self, title: str, content: QWidget, *, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.content = content
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.toggle.clicked.connect(self._apply)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.toggle)
        layout.addWidget(content)
        self.title = title
        self._apply(expanded)

    def _apply(self, expanded: bool):
        self.content.setVisible(expanded)
        self.toggle.setText(("▾  " if expanded else "▸  ") + self.title)


class VideoInspector(QDialog):
    """Floating raw-video player. Playback time drives a synchronized plot cursor."""

    frameChanged = Signal(int)
    timeChanged = Signal(float)
    message = Signal(str)

    def __init__(self, raw_folder: str, camera_count: int, fps: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Movement Lab — Video Inspector")
        self.resize(980, 760)
        self.raw_folder = Path(raw_folder) if raw_folder else Path()
        self.camera_count = max(1, int(camera_count))
        self.fps = float(fps) if np.isfinite(fps) and fps > 0 else 60.0
        self._duration_ms = 0
        self._last_emitted_frame: int | None = None

        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.camera = QComboBox()
        for i in range(self.camera_count):
            self.camera.addItem(f"Cam-{i}", i)
        self.camera.currentIndexChanged.connect(self.load_camera)
        self.file_label = QLabel("No video loaded")
        self.file_label.setObjectName("subtitle")
        self.back_5 = QPushButton("↶ 5 s")
        self.back_5.setToolTip("Jump backward 5 seconds.")
        self.back_5.clicked.connect(lambda: self.seek_relative(-5.0))
        self.play = QPushButton("▶ PLAY")
        self.play.clicked.connect(self.toggle_play)
        self.forward_5 = QPushButton("5 s ↷")
        self.forward_5.setToolTip("Jump forward 5 seconds.")
        self.forward_5.clicked.connect(lambda: self.seek_relative(5.0))
        self.speed = QComboBox()
        for label, rate in (("0.5×", 0.5), ("1.0×", 1.0), ("1.5×", 1.5), ("2.0×", 2.0)):
            self.speed.addItem(label, rate)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(self._set_speed)
        controls.addWidget(QLabel("Camera"))
        controls.addWidget(self.camera)
        controls.addWidget(self.back_5)
        controls.addWidget(self.play)
        controls.addWidget(self.forward_5)
        controls.addWidget(QLabel("Speed"))
        controls.addWidget(self.speed)
        controls.addWidget(self.file_label, 1)
        root.addLayout(controls)

        if MULTIMEDIA_AVAILABLE:
            self.video = QVideoWidget()
            root.addWidget(self.video, 1)
            self.audio = QAudioOutput(self)
            self.audio.setMuted(True)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video)
            self.player.positionChanged.connect(self._position_changed)
            self.player.durationChanged.connect(self._duration_changed)
            self.player.playbackStateChanged.connect(self._state_changed)
        else:
            self.player = None
            unavailable = QLabel("Qt Multimedia is unavailable in this PySide6 installation. The Movement Lab still works; only raw-video playback is disabled.")
            unavailable.setWordWrap(True)
            root.addWidget(unavailable, 1)

        seek_row = QHBoxLayout()
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setRange(0, 1000)
        self.position.sliderMoved.connect(self._seek_slider)
        self.time_label = QLabel("00:00.000  •  frame 0")
        seek_row.addWidget(self.position, 1)
        seek_row.addWidget(self.time_label)
        root.addLayout(seek_row)

        self.load_camera()

    def _find_camera_video(self, index: int) -> Path | None:
        if not self.raw_folder.is_dir():
            return None
        files = [p for p in self.raw_folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
        patterns = [re.compile(rf"Cam[-_]?{index}(?!\d)", re.I), re.compile(rf"camera[-_]?{index}(?!\d)", re.I)]
        matches = [p for p in files if any(rx.search(p.stem) for rx in patterns)]
        if not matches:
            return None
        return sorted(matches)[0]

    def load_camera(self):
        if self.player is None:
            return
        idx = int(self.camera.currentData() or 0)
        path = self._find_camera_video(idx)
        if path is None:
            self.file_label.setText(f"No Cam-{idx} video found in selected folder")
            self.player.setSource(QUrl())
            return
        self.file_label.setText(path.name)
        self.player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self.message.emit(f"Video Inspector loaded Cam-{idx}: {path.name}")

    def toggle_play(self):
        if self.player is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek_relative(self, seconds: float):
        if self.player is None:
            return
        target = int(self.player.position() + float(seconds) * 1000.0)
        if self._duration_ms > 0:
            target = min(target, self._duration_ms)
        self.player.setPosition(max(0, target))

    def _set_speed(self):
        if self.player is not None:
            self.player.setPlaybackRate(float(self.speed.currentData() or 1.0))

    def _state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState if self.player else False
        self.play.setText("⏸ PAUSE" if playing else "▶ PLAY")

    def _duration_changed(self, value: int):
        self._duration_ms = max(0, int(value))

    def _position_changed(self, ms: int):
        if self._duration_ms > 0 and not self.position.isSliderDown():
            self.position.setValue(int(1000 * ms / self._duration_ms))
        seconds = max(0.0, ms / 1000.0)
        frame = max(0, int(round(seconds * self.fps)))
        minute = int(seconds // 60)
        sec = seconds - minute * 60
        self.time_label.setText(f"{minute:02d}:{sec:06.3f}  •  approx. frame {frame:,}")
        self.timeChanged.emit(seconds)
        if frame != self._last_emitted_frame:
            self._last_emitted_frame = frame
            self.frameChanged.emit(frame)

    def _seek_slider(self, value: int):
        if self.player is not None and self._duration_ms > 0:
            self.player.setPosition(int(self._duration_ms * value / 1000))


class MovementLab(QWidget):
    message = Signal(str)

    TABLE_COLUMNS = [
        "keep", "movement_label", "set_index", "sequence_position", "outcome",
        "bodypart", "primary_axis", "start_frame", "end_frame",
        "start_time_seconds", "end_time_seconds", "duration_seconds", "peak_count",
        "displacement_3d", "path_length_3d", "mean_velocity_3d", "peak_velocity_3d",
        "signal_min_frame", "signal_max_frame", "phase_order",
    ]

    DEFAULT_SEQUENCE = [
        "Shoulder flexion / extension",
        "Movement 2",
        "Movement 3",
        "Movement 4",
        "Movement 5",
    ]

    def __init__(self, peak_lab=None, settings=None, parent=None):
        super().__init__(parent)
        self.peak_lab = peak_lab
        self.settings = settings
        self.df: pd.DataFrame | None = None
        self.source_path: Path | None = None
        self.rows: list[dict] = []
        self._history: list[list[dict]] = []
        self._full_start = 0
        self._full_end = 0
        self._last_zoom: tuple[float, float] | None = None
        self._html_path: Path | None = None
        self._plotly_js_path: Path | None = None
        self._video_cursor_frame: int | None = None
        self._video_dialog: VideoInspector | None = None
        self._sequence_cursor = 0
        self._current_set = 1
        self._refreshing_table = False
        self.theme = "dark"

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        source_row = QHBoxLayout()
        self.csv_path = PathRow("Triangulated 3D CSV", mode="file", filter_text="CSV files (*.csv)")
        self.load_button = QPushButton("LOAD CSV")
        self.load_button.setObjectName("accentButton")
        self.load_button.clicked.connect(self.load_csv)
        self.use_peak_source = QPushButton("USE PEAK LAB SOURCE")
        self.use_peak_source.clicked.connect(self.use_peak_lab_source)
        self.save_session_button = QPushButton("SAVE SESSION")
        self.save_session_button.clicked.connect(self.save_session)
        self.open_session_button = QPushButton("OPEN SESSION")
        self.open_session_button.clicked.connect(self.open_session)
        source_row.addWidget(self.csv_path, 1)
        source_row.addWidget(self.load_button)
        source_row.addWidget(self.use_peak_source)
        source_row.addWidget(self.open_session_button)
        source_row.addWidget(self.save_session_button)
        root.addLayout(source_row)

        hint = QLabel("MOVEMENT LAB: 1) load the same 3D CSV used for review, 2) choose bodypart/axis, 3) select a movement window on the plot, 4) label + add it, and 5) optionally open the matched raw video to inspect the same time point. The video timeline, ±5 s controls, and playback speed all keep the plot cursor synchronized.")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        workspace = QSplitter(Qt.Orientation.Horizontal)
        controls = QWidget()
        controls.setMinimumWidth(330)
        controls.setMaximumWidth(460)
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(0, 0, 6, 0)
        cl.setSpacing(7)

        signal_group = QGroupBox("")
        signal_form = QFormLayout(signal_group)
        self.bodypart = QComboBox()
        self.axis = QComboBox(); self.axis.addItems(["x", "y", "z"]); self.axis.setCurrentText("z")
        trace_row = QWidget(); tr = QHBoxLayout(trace_row); tr.setContentsMargins(0,0,0,0)
        self.show_x = QCheckBox("X"); self.show_y = QCheckBox("Y"); self.show_z = QCheckBox("Z"); self.show_z.setChecked(True)
        for box in (self.show_x, self.show_y, self.show_z): tr.addWidget(box)
        tr.addStretch(1)
        self.overview_slider = QCheckBox("Timeline slider"); self.overview_slider.setChecked(True)
        signal_form.addRow("Bodypart", self.bodypart)
        signal_form.addRow("Analysis axis", self.axis)
        signal_form.addRow("Visible traces", trace_row)
        signal_form.addRow(self.overview_slider)
        cl.addWidget(CollapsiblePanel("SIGNAL / VIEW", signal_group, expanded=True))

        protocol_group = QGroupBox("")
        pg = QVBoxLayout(protocol_group)
        pform = QFormLayout()
        self.protocol_name = QLineEdit(self._remembered("movement/protocol_name", "Passive movement protocol"))
        self.sequence_editor = QPlainTextEdit()
        self.sequence_editor.setMaximumHeight(120)
        remembered_seq = self._remembered("movement/default_sequence", "")
        self.sequence_editor.setPlainText(remembered_seq or "\n".join(self.DEFAULT_SEQUENCE))
        self.sequence_editor.textChanged.connect(self._refresh_sequence)
        pform.addRow("Protocol", self.protocol_name)
        pform.addRow("Movement order", self.sequence_editor)
        pg.addLayout(pform)
        proto_buttons = QHBoxLayout()
        self.remember_protocol = QPushButton("REMEMBER DEFAULT")
        self.remember_protocol.clicked.connect(self.remember_default_protocol)
        self.reset_protocol = QPushButton("RESET TEMPLATE")
        self.reset_protocol.clicked.connect(self.reset_protocol_template)
        proto_buttons.addWidget(self.remember_protocol); proto_buttons.addWidget(self.reset_protocol)
        pg.addLayout(proto_buttons)
        note = QLabel("One movement per line. Only the first passive label is prefilled from your current design; edit the remaining placeholders to match the lab's actual recording order.")
        note.setObjectName("subtitle"); note.setWordWrap(True); pg.addWidget(note)
        cl.addWidget(CollapsiblePanel("MOVEMENT PROTOCOL", protocol_group, expanded=True))

        range_group = QGroupBox("")
        rg = QGridLayout(range_group)
        self.range_start = QSpinBox(); self.range_start.setRange(0,2_000_000_000)
        self.range_end = QSpinBox(); self.range_end.setRange(0,2_000_000_000)
        self.pick_range = QPushButton("SELECT WINDOW ON PLOT"); self.pick_range.setObjectName("accentButton"); self.pick_range.setCheckable(True)
        self.pick_range.toggled.connect(self._range_mode_toggled)
        self.use_zoom = QPushButton("USE CURRENT ZOOM"); self.use_zoom.clicked.connect(self.use_current_zoom)
        self.full_range = QPushButton("FULL RANGE"); self.full_range.clicked.connect(self.use_full_range)
        self.range_summary = QLabel("No range loaded"); self.range_summary.setObjectName("subtitle"); self.range_summary.setWordWrap(True)
        rg.addWidget(QLabel("Start"),0,0); rg.addWidget(self.range_start,0,1)
        rg.addWidget(QLabel("End"),1,0); rg.addWidget(self.range_end,1,1)
        rg.addWidget(self.pick_range,2,0,1,2)
        rg.addWidget(self.use_zoom,3,0); rg.addWidget(self.full_range,3,1)
        rg.addWidget(self.range_summary,4,0,1,2)
        cl.addWidget(CollapsiblePanel("MOVEMENT WINDOW", range_group, expanded=True))

        label_group = QGroupBox("")
        lf = QFormLayout(label_group)
        self.movement_label = QComboBox()
        self.set_index = QSpinBox(); self.set_index.setRange(1,100000); self.set_index.setValue(1)
        self.outcome = QComboBox(); self.outcome.addItems(["Not scored", "Success", "Failure"])
        self.phase_math = QCheckBox("Estimate signal extrema / phase order")
        self.phase_math.setChecked(True)
        self.add_window = QPushButton("ADD MOVEMENT WINDOW + NEXT")
        self.add_window.setObjectName("peakButton")
        self.add_window.clicked.connect(self.add_movement_window)
        self.next_label = QPushButton("NEXT LABEL")
        self.next_label.clicked.connect(self.advance_sequence)
        lf.addRow("Movement", self.movement_label)
        lf.addRow("Set #", self.set_index)
        lf.addRow("Outcome", self.outcome)
        lf.addRow(self.phase_math)
        lf.addRow(self.add_window)
        lf.addRow(self.next_label)
        cl.addWidget(CollapsiblePanel("LABEL MOVEMENT", label_group, expanded=True))

        video_group = QGroupBox("")
        vg = QGridLayout(video_group)
        self.raw_folder = PathRow("Exact raw recording folder", mode="folder")
        self.camera_count = QSpinBox(); self.camera_count.setRange(1,32); self.camera_count.setValue(int(self._remembered("camera/count", 4)))
        self.track_video = QCheckBox("Track video with vertical plot cursor"); self.track_video.setChecked(True)
        self.open_video = QPushButton("🎥  OPEN VIDEO INSPECTOR")
        self.open_video.clicked.connect(self.open_video_inspector)
        vg.addWidget(QLabel("Raw videos"),0,0); vg.addWidget(self.raw_folder,0,1)
        vg.addWidget(QLabel("Camera count"),1,0); vg.addWidget(self.camera_count,1,1)
        vg.addWidget(self.track_video,2,0,1,2)
        vg.addWidget(self.open_video,3,0,1,2)
        video_help = QLabel("Default matching uses the recording ID from the loaded 3D CSV and the raw-video paths remembered from Triangulation. You can always browse to a different folder manually.")
        video_help.setObjectName("subtitle")
        video_help.setWordWrap(True)
        vg.addWidget(video_help,4,0,1,2)
        cl.addWidget(CollapsiblePanel("VIDEO INSPECTION", video_group, expanded=True))
        cl.addStretch(1)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setWidget(controls); scroll.setMinimumWidth(340); scroll.setMaximumWidth(470)
        workspace.addWidget(scroll)

        right = QSplitter(Qt.Orientation.Vertical)
        plot_panel = QWidget(); pl = QVBoxLayout(plot_panel); pl.setContentsMargins(0,0,0,0)
        ph = QHBoxLayout(); self.plot_title = QLabel("MOVEMENT LAB"); self.plot_title.setObjectName("plotTitle")
        self.plot_status = QLabel("Load a 3D CSV to begin"); self.plot_status.setObjectName("subtitle")
        ph.addWidget(self.plot_title); ph.addStretch(1); ph.addWidget(self.plot_status); pl.addLayout(ph)
        if WEBENGINE_AVAILABLE:
            self.web = QWebEngineView(); self.bridge = MovementPlotBridge(self)
            self.bridge.selection.connect(self._selection_from_plot); self.bridge.zoomRange.connect(self._zoom_from_plot)
            self.channel = QWebChannel(self.web.page()); self.channel.registerObject("bridge", self.bridge); self.web.page().setWebChannel(self.channel)
            pl.addWidget(self.web,1)
        else:
            self.web = None; no = QLabel("QtWebEngine is unavailable; embedded Movement Lab Plotly view is disabled."); no.setWordWrap(True); pl.addWidget(no,1)
        right.addWidget(plot_panel)

        table_panel = QWidget(); tl = QVBoxLayout(table_panel); tl.setContentsMargins(0,0,0,0)
        th = QHBoxLayout(); title = QLabel("MOVEMENT DATASET"); title.setObjectName("sectionTitle")
        self.table_count = QLabel("0 movement(s)"); self.table_count.setObjectName("subtitle")
        th.addWidget(title); th.addStretch(1); th.addWidget(self.table_count); tl.addLayout(th)
        self.table = QTableWidget(0, len(self.TABLE_COLUMNS)); self.table.setHorizontalHeaderLabels(self.TABLE_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemChanged.connect(self._table_item_changed)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        tl.addWidget(self.table,1)
        tb = QHBoxLayout()
        self.remove = QPushButton("REMOVE SELECTED"); self.remove.clicked.connect(self.remove_selected)
        self.undo = QPushButton("↶ UNDO"); self.undo.clicked.connect(self.undo_action)
        self.export_csv = QPushButton("EXPORT CSV"); self.export_csv.setObjectName("runButton"); self.export_csv.clicked.connect(self.export_csv_file)
        self.export_mat = QPushButton("EXPORT MAT"); self.export_mat.setObjectName("runButton"); self.export_mat.clicked.connect(self.export_mat_file)
        tb.addWidget(self.remove); tb.addWidget(self.undo); tb.addStretch(1); tb.addWidget(self.export_csv); tb.addWidget(self.export_mat); tl.addLayout(tb)
        right.addWidget(table_panel); right.setSizes([560,250])
        workspace.addWidget(right); workspace.setSizes([380,1050])
        root.addWidget(workspace,1)

        self.bodypart.currentTextChanged.connect(lambda _: self.render_plot())
        self.axis.currentTextChanged.connect(lambda _: self.render_plot())
        self.show_x.toggled.connect(lambda _: self.render_plot()); self.show_y.toggled.connect(lambda _: self.render_plot()); self.show_z.toggled.connect(lambda _: self.render_plot())
        self.overview_slider.toggled.connect(lambda _: self.render_plot())
        self.range_start.valueChanged.connect(lambda _: self.update_range_summary())
        self.range_end.valueChanged.connect(lambda _: self.update_range_summary())
        self._refresh_sequence()

    def _remembered(self, key: str, default=""):
        if self.settings is None:
            return default
        value = self.settings.value(key, default)
        return default if value is None else value

    def set_theme(self, theme: str):
        self.theme = theme if theme in {"dark", "light"} else "dark"
        if self.df is not None:
            self.render_plot()

    def set_source_path(self, path: str):
        if path:
            self.csv_path.setText(path)

    def use_peak_lab_source(self):
        path = getattr(self.peak_lab, "source_path", None)
        if path:
            self.csv_path.setText(str(path)); self.load_csv()
        else:
            QMessageBox.information(self, "No Peak Lab source", "Load a CSV in Peak Lab first, or browse to a 3D CSV here.")

    def load_csv(self):
        path = Path(self.csv_path.text())
        if not path.is_file():
            QMessageBox.warning(self, "CSV not found", "Select an existing triangulated 3D CSV."); return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            df = pd.read_csv(path)
            if "frame" not in df.columns: raise KeyError("CSV must contain a frame column.")
            parts = infer_bodyparts(df.columns)
            if not parts: raise KeyError("No complete bodypart_x/bodypart_y/bodypart_z sets were found.")
            for col in [c for c in df.columns if re.match(r"^.+_[xyz]$", str(c))]: df[col] = pd.to_numeric(df[col], errors="coerce")
            df["frame"] = pd.to_numeric(df["frame"], errors="raise").astype(int)
            self.df = df; self.source_path = path
            self._video_cursor_frame = None
            if self._video_dialog is not None:
                self._video_dialog.close()
                self._video_dialog = None
            self._auto_match_raw_folder()
            self.bodypart.blockSignals(True); self.bodypart.clear(); self.bodypart.addItems(parts); self.bodypart.blockSignals(False)
            self._full_start = int(df.frame.min()); self._full_end = int(df.frame.max())
            for box in (self.range_start, self.range_end): box.setRange(self._full_start, self._full_end)
            self.range_start.setValue(self._full_start); self.range_end.setValue(self._full_end)
            self.update_range_summary(); self.render_plot(); self.message.emit(f"Movement Lab loaded: {path.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Could not load Movement Lab CSV", str(exc))
        finally:
            while QApplication.overrideCursor() is not None: QApplication.restoreOverrideCursor()

    def _recording_token(self) -> str:
        if self.source_path is None:
            return ""
        candidates = [self.source_path.parent.parent.name, self.source_path.parent.name, self.source_path.stem]
        for text in candidates:
            match = re.search(r"(?<!\d)(\d{8}_\d{6})(?!\d)", str(text))
            if match:
                return match.group(1)
        return self.source_path.parent.parent.name

    @staticmethod
    def _folder_recording_token(folder: Path) -> str:
        match = re.search(r"(?<!\d)(\d{8}_\d{6})(?!\d)", folder.name)
        return match.group(1) if match else ""

    def _auto_match_raw_folder(self):
        """Populate raw video only when the recording timestamp matches exactly."""
        token = self._recording_token()
        if not token:
            return
        candidates: list[Path] = []
        remembered_exact = str(self._remembered("tri/raw_folder", "") or "").strip()
        if remembered_exact:
            exact = Path(remembered_exact)
            if exact.is_dir() and self._folder_recording_token(exact) == token:
                candidates.append(exact)
        remembered_root = str(self._remembered("tri/raw_root", "") or "").strip()
        if remembered_root:
            root = Path(remembered_root)
            if root.is_dir():
                try:
                    candidates.extend(
                        p for p in root.iterdir()
                        if p.is_dir() and self._folder_recording_token(p) == token
                    )
                except OSError:
                    pass
        # Remove duplicates while preserving priority (remembered exact first).
        unique: list[Path] = []
        seen: set[str] = set()
        for folder in candidates:
            key = str(folder.resolve()).lower()
            if key not in seen:
                seen.add(key); unique.append(folder)
        if len(unique) == 1:
            self.raw_folder.setText(str(unique[0]))
            self.message.emit(f"Movement Lab exact raw-video match ({token}) -> {unique[0]}")
        elif len(unique) > 1:
            self.message.emit(f"Movement Lab found multiple exact raw-video matches for {token}; choose the folder manually.")

    def _frame_for_video_seconds(self, seconds: float) -> int:
        if self.df is None or self.df.empty:
            return max(0, int(round(seconds * self._fps())))
        frames = self.df["frame"].to_numpy(dtype=int)
        if "time_seconds" in self.df.columns:
            times = pd.to_numeric(self.df["time_seconds"], errors="coerce").to_numpy(dtype=float)
            valid = np.isfinite(times)
            if valid.any():
                base = float(times[valid][0])
                relative = times - base
                valid_idx = np.flatnonzero(np.isfinite(relative))
                nearest = valid_idx[int(np.argmin(np.abs(relative[valid_idx] - float(seconds))))]
                return int(frames[nearest])
        return int(frames[0] + round(float(seconds) * self._fps()))

    def _fps(self) -> float:
        if self.df is not None and "time_seconds" in self.df.columns:
            t = pd.to_numeric(self.df["time_seconds"], errors="coerce").to_numpy(float)
            d = np.diff(t); d = d[np.isfinite(d) & (d > 0)]
            if d.size: return float(1.0 / np.median(d))
        return 60.0

    def _refresh_sequence(self):
        lines = [x.strip() for x in self.sequence_editor.toPlainText().splitlines() if x.strip()]
        current = self.movement_label.currentText() if self.movement_label.count() else ""
        self.movement_label.blockSignals(True); self.movement_label.clear(); self.movement_label.addItems(lines or self.DEFAULT_SEQUENCE); self.movement_label.blockSignals(False)
        if current and self.movement_label.findText(current) >= 0: self.movement_label.setCurrentText(current)
        self._sequence_cursor = max(0, self.movement_label.currentIndex())

    def remember_default_protocol(self):
        if self.settings is not None:
            self.settings.setValue("movement/protocol_name", self.protocol_name.text())
            self.settings.setValue("movement/default_sequence", self.sequence_editor.toPlainText())
        self.message.emit("Movement protocol remembered as the default for future drafts.")

    def reset_protocol_template(self):
        self.sequence_editor.setPlainText("\n".join(self.DEFAULT_SEQUENCE)); self._current_set = 1; self.set_index.setValue(1)

    def advance_sequence(self):
        count = self.movement_label.count()
        if count < 1: return
        i = self.movement_label.currentIndex() + 1
        if i >= count:
            i = 0; self._current_set = self.set_index.value() + 1; self.set_index.setValue(self._current_set)
        self.movement_label.setCurrentIndex(i); self._sequence_cursor = i

    def _range_mode_toggled(self, checked: bool):
        self.pick_range.setText("CANCEL WINDOW PICK" if checked else "SELECT WINDOW ON PLOT")
        if self.web is not None:
            mode = "select" if checked else "zoom"
            self.web.page().runJavaScript(f"var p=document.getElementById('movementPlot'); if(p&&window.Plotly) Plotly.relayout(p, {{dragmode:'{mode}'}});")

    def _selection_from_plot(self, xmin: float, xmax: float):
        if self.df is None: return
        start=max(self._full_start,int(round(min(xmin,xmax)))); end=min(self._full_end,int(round(max(xmin,xmax))))
        self.range_start.setValue(start); self.range_end.setValue(end)
        self.pick_range.blockSignals(True); self.pick_range.setChecked(False); self.pick_range.blockSignals(False); self.pick_range.setText("SELECT WINDOW ON PLOT")
        self.update_range_summary(); self.render_plot()

    def _zoom_from_plot(self, xmin: float, xmax: float): self._last_zoom=(xmin,xmax)

    def use_current_zoom(self):
        if self._last_zoom is None:
            QMessageBox.information(self,"No zoom window","Zoom the plot first, then press USE CURRENT ZOOM."); return
        self._selection_from_plot(*self._last_zoom)

    def use_full_range(self):
        if self.df is None: return
        self.range_start.setValue(self._full_start); self.range_end.setValue(self._full_end); self.render_plot()

    def _row_near(self, frame: int) -> pd.Series:
        assert self.df is not None
        frames=self.df["frame"].to_numpy(int); return self.df.iloc[int(np.argmin(np.abs(frames-int(frame))))]

    def _time_at(self, frame: int) -> float:
        if self.df is None or "time_seconds" not in self.df.columns: return np.nan
        row=self._row_near(frame); value=row.get("time_seconds",np.nan); return float(value) if pd.notna(value) else np.nan

    def _peak_count(self, start: int, end: int) -> int:
        rows = getattr(self.peak_lab, "session_rows", []) if self.peak_lab is not None else []
        bp = self.bodypart.currentText()
        return sum(1 for r in rows if r.get("keep",True) and bool(r.get("_confirmed", True)) and r.get("bodypart")==bp and start <= int(r.get("frame",-1)) <= end)

    def update_range_summary(self):
        if self.df is None: self.range_summary.setText("No range loaded"); return
        start,end=sorted((self.range_start.value(),self.range_end.value())); t0=self._time_at(start); t1=self._time_at(end)
        time_text=""
        if np.isfinite(t0) and np.isfinite(t1): time_text=f" • {t0:.3f}–{t1:.3f} s • {max(0,t1-t0):.3f} s"
        self.range_summary.setText(f"Frames {start:,}–{end:,}{time_text} • {self._peak_count(start,end)} reviewed peak(s)")

    def _movement_metrics(self, start: int, end: int, bp: str, axis: str) -> dict:
        assert self.df is not None
        sub=self.df[(self.df.frame>=start)&(self.df.frame<=end)].copy()
        t0=self._time_at(start); t1=self._time_at(end); duration=float(t1-t0) if np.isfinite(t0) and np.isfinite(t1) else np.nan
        xyz=sub[[f"{bp}_x",f"{bp}_y",f"{bp}_z"]].to_numpy(float)
        finite=np.isfinite(xyz).all(axis=1); valid=xyz[finite]
        displacement=path_length=mean_vel=peak_vel=np.nan
        if len(valid)>=2:
            displacement=float(np.linalg.norm(valid[-1]-valid[0])); steps=np.linalg.norm(np.diff(valid,axis=0),axis=1); path_length=float(np.nansum(steps))
        if "time_seconds" in sub.columns:
            tt=pd.to_numeric(sub["time_seconds"],errors="coerce").to_numpy(float); pair=finite[:-1]&finite[1:]&np.isfinite(tt[:-1])&np.isfinite(tt[1:])
            dt=np.diff(tt); dist=np.linalg.norm(np.diff(xyz,axis=0),axis=1); good=pair&(dt>0)
            if np.any(good):
                velocities=dist[good]/dt[good]; mean_vel=float(np.nanmean(velocities)); peak_vel=float(np.nanmax(velocities))
        min_frame=max_frame=""; phase=""
        if self.phase_math.isChecked():
            vals=sub[f"{bp}_{axis}"].to_numpy(float); frames=sub.frame.to_numpy(int); ok=np.isfinite(vals)
            if np.any(ok):
                v=vals[ok]; f=frames[ok]; min_frame=int(f[int(np.argmin(v))]); max_frame=int(f[int(np.argmax(v))]); phase="max→min" if max_frame<min_frame else "min→max"
        return {"start_time_seconds":t0,"end_time_seconds":t1,"duration_seconds":duration,"displacement_3d":displacement,"path_length_3d":path_length,"mean_velocity_3d":mean_vel,"peak_velocity_3d":peak_vel,"signal_min_frame":min_frame,"signal_max_frame":max_frame,"phase_order":phase}

    def add_movement_window(self):
        if self.df is None:
            QMessageBox.information(self,"Load data first","Load a 3D CSV before adding movement windows."); return
        start,end=sorted((self.range_start.value(),self.range_end.value())); bp=self.bodypart.currentText(); axis=self.axis.currentText(); label=self.movement_label.currentText().strip()
        if not label:
            QMessageBox.warning(self,"Movement label","Enter at least one movement label in the protocol."); return
        self._history.append(copy.deepcopy(self.rows))
        metrics=self._movement_metrics(start,end,bp,axis)
        record={"keep":True,"movement_label":label,"set_index":self.set_index.value(),"sequence_position":self.movement_label.currentIndex()+1,"outcome":self.outcome.currentText(),"bodypart":bp,"primary_axis":axis,"start_frame":start,"end_frame":end,"peak_count":self._peak_count(start,end),"_uid":uuid.uuid4().hex}
        record.update(metrics); self.rows.append(record); self.rows.sort(key=lambda r:int(r.get("start_frame",0)))
        self._refresh_table(); self.render_plot(); self.advance_sequence(); self.message.emit(f"Added movement window: {label} | frames {start}-{end}")

    def remove_selected(self):
        idx=sorted({x.row() for x in self.table.selectedIndexes()},reverse=True)
        if not idx:return
        self._history.append(copy.deepcopy(self.rows))
        for i in idx:
            if 0<=i<len(self.rows): self.rows.pop(i)
        self._refresh_table(); self.render_plot()

    def undo_action(self):
        if not self._history:
            QMessageBox.information(self,"Nothing to undo","No Movement Lab edit is available to undo."); return
        self.rows=self._history.pop(); self._refresh_table(); self.render_plot()

    def _refresh_table(self):
        self._refreshing_table = True
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(self.rows))
            for r,record in enumerate(self.rows):
                for c,col in enumerate(self.TABLE_COLUMNS):
                    if col=="keep":
                        item=QTableWidgetItem(""); item.setCheckState(Qt.CheckState.Checked if record.get("keep",True) else Qt.CheckState.Unchecked)
                    else:
                        value=record.get(col,""); value="" if isinstance(value,float) and np.isnan(value) else value; item=QTableWidgetItem(str(value))
                    self.table.setItem(r,c,item)
        finally:
            self.table.blockSignals(False)
            self._refreshing_table = False
        self.table_count.setText(f"{len(self.rows)} movement(s)")

    def _table_item_changed(self, item: QTableWidgetItem):
        if self._refreshing_table or not (0 <= item.row() < len(self.rows)):
            return
        col = self.TABLE_COLUMNS[item.column()]
        record = self.rows[item.row()]
        if col == "keep":
            record["keep"] = item.checkState() == Qt.CheckState.Checked
            self.render_plot()
            return
        text = item.text()
        numeric_cols = {
            "set_index", "sequence_position", "start_frame", "end_frame", "peak_count",
            "start_time_seconds", "end_time_seconds", "duration_seconds", "displacement_3d",
            "path_length_3d", "mean_velocity_3d", "peak_velocity_3d",
            "signal_min_frame", "signal_max_frame",
        }
        if col in numeric_cols and text.strip():
            try:
                value = float(text)
                if col in {"set_index", "sequence_position", "start_frame", "end_frame", "peak_count", "signal_min_frame", "signal_max_frame"}:
                    value = int(round(value))
                record[col] = value
            except ValueError:
                record[col] = text
        else:
            record[col] = text
        if col in {"movement_label", "start_frame", "end_frame"}:
            self.render_plot()

    def _sync_keep(self):
        for i,r in enumerate(self.rows):
            item=self.table.item(i,0)
            if item:r["keep"]=item.checkState()==Qt.CheckState.Checked

    def render_plot(self):
        if self.df is None or self.web is None:return
        try:
            bp=self.bodypart.currentText(); axis=self.axis.currentText(); start,end=sorted((self.range_start.value(),self.range_end.value())); sub=self.df[(self.df.frame>=start)&(self.df.frame<=end)]
            if sub.empty or not bp:return
            palette=plot_palette(self.theme); movement_colors=movement_trace_colors(self.theme); fig=go.Figure(); visible={"x":self.show_x.isChecked(),"y":self.show_y.isChecked(),"z":self.show_z.isChecked()}
            if not any(visible.values()):visible[axis]=True
            for a in ("x","y","z"):
                if visible[a]:fig.add_trace(go.Scattergl(x=sub.frame,y=sub[f"{bp}_{a}"],mode="lines",name=a.upper(),connectgaps=False,line=dict(color=movement_colors[a],width=2.2 if a==axis else 1.35),opacity=1 if a==axis else .82))
            shapes=[]
            cursor=self._video_cursor_frame if self._video_cursor_frame is not None else start
            shapes.append(dict(type="line",xref="x",yref="paper",x0=cursor,x1=cursor,y0=0,y1=1,line=dict(color=palette["peak"],width=2,dash="dot"),visible=self.track_video.isChecked() and self._video_cursor_frame is not None))
            for rec in self.rows:
                if not rec.get("keep",True):continue
                rs,re=int(rec.get("start_frame",0)),int(rec.get("end_frame",0))
                if re<start or rs>end:continue
                shapes.append(dict(type="rect",xref="x",yref="paper",x0=rs,x1=re,y0=0,y1=1,fillcolor=palette["peak"],opacity=.12,line=dict(color=palette["peak"],width=1)))
                fig.add_annotation(x=(rs+re)/2,y=1,xref="x",yref="paper",text=str(rec.get("movement_label","")),showarrow=False,yshift=10,font=dict(color=palette["text"],size=10))
            fig.update_layout(paper_bgcolor=palette["paper"],plot_bgcolor=palette["plot"],font=dict(color=palette["text"],family="Courier New"),xaxis_title="Frame",yaxis_title=f"{bp} 3D coordinate",dragmode="select" if self.pick_range.isChecked() else "zoom",margin=dict(l=62,r=18,t=46,b=60),legend=dict(orientation="h",y=1.02),shapes=shapes,uirevision=f"movement-{bp}-{axis}-{start}-{end}-{self.theme}")
            fig.update_xaxes(rangeslider_visible=self.overview_slider.isChecked(),gridcolor=palette["grid"],zerolinecolor=palette["grid"]); fig.update_yaxes(gridcolor=palette["grid"],zerolinecolor=palette["grid"])
            if self._plotly_js_path is None:
                cache=Path(tempfile.gettempdir())/"motion_pipeline_gui"; cache.mkdir(parents=True,exist_ok=True); js=cache/"plotly.min.js"
                if not js.is_file():js.write_text(get_plotlyjs(),encoding="utf-8")
                self._plotly_js_path=js
            html=fig.to_html(include_plotlyjs=False,full_html=True,div_id="movementPlot",config={"displaylogo":False,"scrollZoom":True,"responsive":True})
            html=html.replace("</head>",f'<script src="{self._plotly_js_path.resolve().as_uri()}"></script></head>')
            bridge=r'''<script src="qrc:///qtwebchannel/qwebchannel.js"></script><script>
new QWebChannel(qt.webChannelTransport,function(channel){window.bridge=channel.objects.bridge;var p=document.getElementById('movementPlot');
p.on('plotly_selected',function(d){if(!d)return;if(d.range&&d.range.x){bridge.receiveSelection(JSON.stringify({xmin:Number(d.range.x[0]),xmax:Number(d.range.x[1])}));return;}if(d.points&&d.points.length){var xs=d.points.map(q=>Number(q.x)).filter(Number.isFinite);if(xs.length)bridge.receiveSelection(JSON.stringify({xmin:Math.min(...xs),xmax:Math.max(...xs)}));}});
p.on('plotly_relayout',function(d){var a=d['xaxis.range[0]'],b=d['xaxis.range[1]'];if(a!==undefined&&b!==undefined)bridge.receiveZoom(JSON.stringify({xmin:Number(a),xmax:Number(b)}));});});</script>'''
            html=html.replace("</body>",bridge+"</body>")
            if self._html_path:
                try:self._html_path.unlink(missing_ok=True)
                except Exception:pass
            f=tempfile.NamedTemporaryFile(mode="w",suffix=".html",prefix="motion_movement_",delete=False,encoding="utf-8"); f.write(html); f.close(); self._html_path=Path(f.name); self.web.load(QUrl.fromLocalFile(str(self._html_path)))
            self.plot_title.setText(f"{bp}  /  {axis.upper()}  /  MOVEMENT WINDOWS"); self.plot_status.setText(f"frames {start:,}–{end:,} • {len(self.rows)} labeled movement(s)"); self.update_range_summary()
        except Exception as exc:self.message.emit(f"Movement plot error: {exc}")

    def open_video_inspector(self):
        if not self.raw_folder.text().strip():
            QMessageBox.warning(self,"Raw video folder","Select the exact raw recording folder containing the camera videos."); return
        folder=Path(self.raw_folder.text())
        if not folder.is_dir():
            QMessageBox.warning(self,"Raw video folder","Select the exact raw recording folder containing the camera videos."); return
        self._video_dialog=VideoInspector(str(folder),self.camera_count.value(),self._fps(),self)
        self._video_dialog.timeChanged.connect(self._video_time_changed)
        self._video_dialog.message.connect(self.message)
        self._video_dialog.show()

    def _video_time_changed(self, seconds: float):
        self._video_frame_changed(self._frame_for_video_seconds(float(seconds)))

    def _video_frame_changed(self, frame: int):
        frame = int(frame)
        if self.df is not None:
            frame = max(self._full_start, min(self._full_end, frame))
        if self._video_cursor_frame == frame:
            return
        self._video_cursor_frame=frame
        if not self.track_video.isChecked() or self.web is None:return
        self.web.page().runJavaScript(f"var p=document.getElementById('movementPlot'); if(p&&window.Plotly) Plotly.relayout(p, {{'shapes[0].x0':{frame},'shapes[0].x1':{frame},'shapes[0].visible':true}});")

    def _export_frame(self) -> pd.DataFrame:
        self._sync_keep(); kept=[r for r in self.rows if r.get("keep",True)]; return pd.DataFrame([{c:r.get(c,"") for c in self.TABLE_COLUMNS} for r in kept],columns=self.TABLE_COLUMNS)

    def export_csv_file(self):
        frame=self._export_frame()
        if frame.empty: QMessageBox.information(self,"Nothing to export","No kept movement rows are available."); return
        default=str((self.source_path.parent if self.source_path else Path.cwd())/"movement_events.csv")
        path,_=QFileDialog.getSaveFileName(self,"Export movement dataset",default,"CSV files (*.csv)")
        if path:frame.to_csv(path,index=False);self.message.emit(f"Exported movement dataset -> {path}")

    def export_mat_file(self):
        frame=self._export_frame()
        if frame.empty: QMessageBox.information(self,"Nothing to export","No kept movement rows are available."); return
        default=str((self.source_path.parent if self.source_path else Path.cwd())/"movement_events.mat")
        path,_=QFileDialog.getSaveFileName(self,"Export movement dataset for MATLAB",default,"MATLAB files (*.mat)")
        if not path:return
        struct={}
        for col in frame.columns:
            num=pd.to_numeric(frame[col],errors="coerce")
            struct[col]=num.to_numpy() if num.notna().sum()==len(frame) else np.asarray(["" if pd.isna(v) else str(v) for v in frame[col]],dtype=object)
        savemat(path,{"movement_events":struct,"source_csv":str(self.source_path or "")},do_compression=True);self.message.emit(f"Exported MATLAB movement dataset -> {path}")

    def save_session(self):
        default=str((self.source_path.parent if self.source_path else Path.cwd())/"movement_session.json")
        path,_=QFileDialog.getSaveFileName(self,"Save Movement Lab session",default,"JSON files (*.json)")
        if not path:return
        payload={"source_csv":str(self.source_path or ""),"raw_folder":self.raw_folder.text(),"camera_count":self.camera_count.value(),"protocol_name":self.protocol_name.text(),"sequence":self.sequence_editor.toPlainText(),"bodypart":self.bodypart.currentText(),"axis":self.axis.currentText(),"rows":self.rows}
        Path(path).write_text(json.dumps(payload,indent=2,allow_nan=True),encoding="utf-8");self.message.emit(f"Saved Movement Lab session -> {path}")

    def open_session(self):
        path,_=QFileDialog.getOpenFileName(self,"Open Movement Lab session","","JSON files (*.json)")
        if not path:return
        try:
            payload=json.loads(Path(path).read_text(encoding="utf-8")); self.csv_path.setText(payload.get("source_csv","")); self.load_csv(); self.raw_folder.setText(payload.get("raw_folder","")); self.camera_count.setValue(int(payload.get("camera_count",4))); self.protocol_name.setText(payload.get("protocol_name","Passive movement protocol")); self.sequence_editor.setPlainText(payload.get("sequence","\n".join(self.DEFAULT_SEQUENCE)))
            bp=payload.get("bodypart","");
            if self.bodypart.findText(bp)>=0:self.bodypart.setCurrentText(bp)
            self.axis.setCurrentText(payload.get("axis","z")); self.rows=list(payload.get("rows",[]));
            for r in self.rows:r.setdefault("_uid",uuid.uuid4().hex)
            self._refresh_table(); self.render_plot(); self.message.emit(f"Opened Movement Lab session -> {path}")
        except Exception as exc:QMessageBox.critical(self,"Could not open Movement Lab session",str(exc))
