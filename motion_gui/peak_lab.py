from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import uuid
import copy

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.offline import get_plotlyjs
from scipy.signal import butter, find_peaks, savgol_filter, sosfiltfilt
from scipy.io import savemat

from PySide6.QtCore import QObject, QUrl, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QScrollArea,
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

from .theme import plot_palette, trace_palette_items
from .widgets import PathRow


class PlotBridge(QObject):
    selection = Signal(float, float)
    clicked = Signal(float)
    zoomRange = Signal(float, float)
    peakSelected = Signal(str)
    peakMoved = Signal(str, float)

    @Slot(str)
    def receiveSelection(self, payload: str):
        try:
            data = json.loads(payload)
            self.selection.emit(float(data["xmin"]), float(data["xmax"]))
        except Exception:
            pass

    @Slot(str)
    def receiveClick(self, payload: str):
        try:
            data = json.loads(payload)
            self.clicked.emit(float(data["x"]))
        except Exception:
            pass

    @Slot(str)
    def receiveZoom(self, payload: str):
        try:
            data = json.loads(payload)
            self.zoomRange.emit(float(data["xmin"]), float(data["xmax"]))
        except Exception:
            pass

    @Slot(str)
    def receivePeak(self, payload: str):
        try:
            data = json.loads(payload)
            self.peakSelected.emit(str(data["uid"]))
        except Exception:
            pass

    @Slot(str)
    def receivePeakMove(self, payload: str):
        try:
            data = json.loads(payload)
            self.peakMoved.emit(str(data["uid"]), float(data["x"]))
        except Exception:
            pass


def infer_bodyparts(columns) -> list[str]:
    axes = {}
    for column in columns:
        match = re.match(r"^(.+)_([xyz])$", str(column))
        if match:
            axes.setdefault(match.group(1), set()).add(match.group(2))
    return sorted(name for name, found in axes.items() if {"x", "y", "z"}.issubset(found))


def contiguous_finite_segments(values: np.ndarray):
    finite = np.isfinite(values)
    indices = np.flatnonzero(finite)
    if not len(indices):
        return
    splits = np.where(np.diff(indices) > 1)[0] + 1
    for segment in np.split(indices, splits):
        if len(segment):
            yield segment


def fill_short_internal_gaps(values: np.ndarray, max_gap: int) -> tuple[np.ndarray, np.ndarray]:
    """Linearly fill only bounded NaN runs up to max_gap samples."""
    arr = np.asarray(values, dtype=float).copy()
    filled_mask = np.zeros(arr.shape, dtype=bool)
    missing = ~np.isfinite(arr)
    i = 0
    while i < len(arr):
        if not missing[i]:
            i += 1
            continue
        start = i
        while i < len(arr) and missing[i]:
            i += 1
        end = i - 1
        gap = end - start + 1
        if start == 0 or end >= len(arr) - 1 or gap > int(max_gap):
            continue
        left = arr[start - 1]
        right = arr[end + 1]
        if not (np.isfinite(left) and np.isfinite(right)):
            continue
        arr[start:end + 1] = np.linspace(left, right, gap + 2)[1:-1]
        filled_mask[start:end + 1] = True
    return arr, filled_mask


def savgol_finite_segments(values: np.ndarray, window: int, polyorder: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float).copy()
    for idx in contiguous_finite_segments(arr):
        segment = arr[idx]
        if len(segment) < 3:
            continue
        w = min(int(window), len(segment) if len(segment) % 2 == 1 else len(segment) - 1)
        if w % 2 == 0:
            w -= 1
        min_w = int(polyorder) + 2
        if min_w % 2 == 0:
            min_w += 1
        if w < min_w or w < 3:
            continue
        arr[idx] = savgol_filter(segment, window_length=w, polyorder=min(int(polyorder), w - 1), mode="interp")
    return arr


def butterworth_finite_segments(values: np.ndarray, fs: float, cutoff_hz: float, order: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float).copy()
    if not np.isfinite(fs) or fs <= 0:
        fs = 60.0
    nyquist = fs / 2.0
    cutoff = min(max(float(cutoff_hz), 1e-6), nyquist * 0.95)
    sos = butter(int(order), cutoff, btype="lowpass", fs=fs, output="sos")
    for idx in contiguous_finite_segments(arr):
        segment = arr[idx]
        if len(segment) < max(12, int(order) * 4):
            continue
        try:
            arr[idx] = sosfiltfilt(sos, segment)
        except ValueError:
            # Short continuous blocks may be too small for filtfilt's padding.
            continue
    return arr


class CollapsiblePanel(QWidget):
    """Small disclosure panel used by Peak Lab's left-side tools."""

    def __init__(self, title: str, content: QWidget, *, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.title = title
        self.content = content
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.toggle.clicked.connect(self._apply_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self._apply_state(expanded)

    def _apply_state(self, expanded: bool):
        self.content.setVisible(bool(expanded))
        arrow = "▾" if expanded else "▸"
        self.toggle.setText(f"{arrow}  {self.title}")


class PeakLab(QWidget):
    message = Signal(str)
    sourceLoaded = Signal(str)

    # Intentionally compact. Source file and data version live at the session level,
    # and detection direction is a control rather than an exported event attribute.
    TABLE_COLUMNS = [
        "keep",
        "event_label",
        "bodypart",
        "event_index",
        "frame",
        "time_seconds",
        "timestamp",
        "x",
        "y",
        "z",
        "velocity_3d",
        "primary_axis",
        "primary_value",
        "prominence",
        "range_start",
        "range_end",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.df: pd.DataFrame | None = None
        self.source_path: Path | None = None
        self.session_rows: list[dict] = []
        self.last_clicked_frame: int | None = None
        self._html_path: Path | None = None
        self._full_start = 0
        self._full_end = 0
        self._auto_label = ""
        self._refreshing_table = False
        self._move_row: int | None = None
        self._selected_peak_uid: str | None = None
        self._last_zoom: tuple[float, float] | None = None
        self._history: list[tuple[str, list[dict]]] = []
        self._plotly_js_path: Path | None = None
        self._busy_cursor_set = False
        self.theme = "dark"

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ------------------------------------------------------------------
        # Source/session row
        # ------------------------------------------------------------------
        source_row = QHBoxLayout()
        self.csv_path = PathRow("Select a triangulated 3D CSV", mode="file", filter_text="CSV files (*.csv)")
        self.load_button = QPushButton("LOAD CSV")
        self.load_button.setObjectName("accentButton")
        self.load_button.setToolTip("Load a triangulated 3D CSV and discover its bodyparts automatically.")
        self.load_button.clicked.connect(self.load_csv)
        self.open_session_button = QPushButton("OPEN SESSION")
        self.open_session_button.setToolTip("Reopen a previously saved Peak Lab JSON session.")
        self.open_session_button.clicked.connect(self.open_session)
        self.save_session_button = QPushButton("SAVE SESSION")
        self.save_session_button.setToolTip("Save the current source, controls, and reviewed event table to JSON.")
        self.save_session_button.clicked.connect(self.save_session)
        self.save_session_with_export = QCheckBox("Save review session with export")
        self.save_session_with_export.setToolTip("When CSV or MAT is exported, also write a separate Peak Lab session JSON beside it.")
        self.save_session_with_export.setChecked(False)
        source_row.addWidget(self.csv_path, 1)
        source_row.addWidget(self.load_button)
        source_row.addWidget(self.open_session_button)
        source_row.addWidget(self.save_session_button)
        source_row.addWidget(self.save_session_with_export)
        root.addLayout(source_row)

        workflow = QLabel(
            "LOAD CSV  →  choose signal  →  select a movement range  →  FIND PEAKS  →  review / move events  →  EXPORT CSV"
        )
        workflow.setObjectName("hintLabel")
        workflow.setWordWrap(True)
        root.addWidget(workflow)
        self.context_bar = QLabel("Source: —  •  Bodypart: —  •  Primary: Z  •  Review: 0 events")
        self.context_bar.setObjectName("subtitle")
        self.context_bar.setWordWrap(True)
        root.addWidget(self.context_bar)

        # ------------------------------------------------------------------
        # Main workspace: compact controls on the left; plot + dataset on right.
        # ------------------------------------------------------------------
        workspace = QSplitter(Qt.Orientation.Horizontal)

        control_panel = QWidget()
        control_panel.setMinimumWidth(315)
        control_panel.setMaximumWidth(430)
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(0, 0, 6, 0)
        control_layout.setSpacing(7)

        signal_group = QGroupBox("")
        signal_form = QFormLayout(signal_group)
        signal_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.bodypart = QComboBox()
        self.primary_axis = QComboBox()
        self.primary_axis.addItems(["None", "x", "y", "z"])
        self.primary_axis.setCurrentText("z")
        signal_form.addRow("Bodypart", self.bodypart)
        signal_form.addRow("Primary axis", self.primary_axis)

        trace_row = QWidget()
        trace_layout = QHBoxLayout(trace_row)
        trace_layout.setContentsMargins(0, 0, 0, 0)
        self.show_x = QCheckBox("X")
        self.show_y = QCheckBox("Y")
        self.show_z = QCheckBox("Z")
        # v0.5.6 defaults to all coordinates because the new layout modes can
        # separate them without forcing X/Y/Z onto one crowded axis.
        self.show_x.setChecked(True)
        self.show_y.setChecked(True)
        self.show_z.setChecked(True)
        trace_layout.addWidget(self.show_x)
        trace_layout.addWidget(self.show_y)
        trace_layout.addWidget(self.show_z)
        trace_layout.addStretch(1)
        signal_form.addRow("Visible traces", trace_row)

        self.trace_layout_mode = QComboBox()
        self.trace_layout_mode.addItem("Overlay", "overlay")
        self.trace_layout_mode.addItem("Separate XYZ", "separate")
        self.trace_layout_mode.addItem("Primary trace on top", "primary_top")
        self.trace_layout_mode.setCurrentIndex(2)
        self.trace_layout_mode.setToolTip("Overlay shares one y-axis; Separate XYZ gives each visible coordinate its own row; Primary trace on top keeps the original single-canvas view and draws the selected peak-detection axis last, thicker, and fully opaque.")
        self.trace_palette = QComboBox()
        for key, name in trace_palette_items():
            self.trace_palette.addItem(name, key)
        signal_form.addRow("Trace layout", self.trace_layout_mode)
        signal_form.addRow("Trace palette", self.trace_palette)

        self.hover_details = QCheckBox("Hover details")
        self.hover_details.setChecked(True)
        self.hover_details.setToolTip("Show/hide frame, elapsed time, timestamp and XYZ values under the mouse.")
        self.overview_slider = QCheckBox("Overview slider")
        self.overview_slider.setChecked(False)
        self.overview_slider.setToolTip("Show/hide the small Plotly range slider below the graph.")
        signal_form.addRow(self.hover_details)
        signal_form.addRow(self.overview_slider)
        self.signal_panel = CollapsiblePanel("SIGNAL / VIEW", signal_group, expanded=True)
        control_layout.addWidget(self.signal_panel)

        cleanup_group = QGroupBox("")
        cleanup_form = QFormLayout(cleanup_group)
        cleanup_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        cleanup_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.fill_short_gaps = QCheckBox("Fill short internal gaps")
        self.fill_short_gaps.setChecked(False)
        self.fill_short_gaps.setToolTip("Linearly interpolate only short NaN gaps that have real data on both sides. Long gaps remain missing.")
        self.max_gap = QSpinBox()
        self.max_gap.setRange(1, 300)
        self.max_gap.setValue(5)
        self.max_gap.setSuffix(" frames")
        self.smoothing = QComboBox()
        self.smoothing.addItem("None", "none")
        self.smoothing.addItem("Savitzky–Golay", "savgol")
        self.smoothing.addItem("Butterworth low-pass", "butter")
        self.savgol_window = QSpinBox()
        self.savgol_window.setRange(5, 501)
        self.savgol_window.setSingleStep(2)
        self.savgol_window.setValue(11)
        self.savgol_poly = QSpinBox()
        self.savgol_poly.setRange(1, 7)
        self.savgol_poly.setValue(2)
        self.butter_cutoff = QDoubleSpinBox()
        self.butter_cutoff.setRange(0.1, 100.0)
        self.butter_cutoff.setDecimals(2)
        self.butter_cutoff.setValue(6.0)
        self.butter_cutoff.setSuffix(" Hz")
        self.butter_order = QSpinBox()
        self.butter_order.setRange(1, 10)
        self.butter_order.setValue(4)
        self.show_raw_reference = QCheckBox("Show raw reference")
        self.show_raw_reference.setChecked(True)
        self.cleanup_apply = QPushButton("APPLY CLEANUP TO VIEW")
        self.cleanup_apply.setObjectName("accentButton")
        self.cleanup_apply.setToolTip("Redraw Peak Lab using the current gap-fill and smoothing settings. FIND PEAKS always uses the current cleanup settings.")
        self.cleanup_note = QLabel("")
        self.cleanup_note.setObjectName("subtitle")
        self.cleanup_note.setWordWrap(True)
        cleanup_form.addRow(self.fill_short_gaps)
        cleanup_form.addRow("Maximum gap", self.max_gap)
        cleanup_form.addRow("Smoothing", self.smoothing)
        cleanup_form.addRow("SavGol window", self.savgol_window)
        cleanup_form.addRow("Polynomial order", self.savgol_poly)
        cleanup_form.addRow("Butter cutoff", self.butter_cutoff)
        cleanup_form.addRow("Butter order", self.butter_order)
        cleanup_form.addRow(self.show_raw_reference)
        cleanup_form.addRow(self.cleanup_apply)
        cleanup_form.addRow(self.cleanup_note)
        self.cleanup_panel = CollapsiblePanel("SIGNAL CLEANUP", cleanup_group, expanded=True)
        control_layout.addWidget(self.cleanup_panel)

        range_group = QGroupBox("")
        range_grid = QGridLayout(range_group)
        self.range_start = QSpinBox()
        self.range_start.setRange(0, 2_000_000_000)
        self.range_end = QSpinBox()
        self.range_end.setRange(0, 2_000_000_000)
        range_grid.addWidget(QLabel("Start"), 0, 0)
        range_grid.addWidget(self.range_start, 0, 1)
        range_grid.addWidget(QLabel("End"), 1, 0)
        range_grid.addWidget(self.range_end, 1, 1)
        self.pick_range = QPushButton("SELECT RANGE ON PLOT")
        self.pick_range.setObjectName("accentButton")
        self.pick_range.setCheckable(True)
        self.pick_range.setToolTip("Turn on box selection. Drag across one movement bout to copy its frames into Start/End.")
        self.pick_range.toggled.connect(self._range_mode_toggled)
        range_grid.addWidget(self.pick_range, 2, 0, 1, 2)

        self.apply_range = QPushButton("APPLY RANGE")
        self.apply_range.setToolTip("Redraw the graph and make Start/End the exact interval used by FIND PEAKS.")
        self.apply_range.clicked.connect(self.render_plot)
        self.use_zoom = QPushButton("USE CURRENT ZOOM")
        self.use_zoom.setToolTip("Copy the Plotly x-axis zoom window into Start/End, then use that same interval for peak finding.")
        self.use_zoom.clicked.connect(self.use_current_zoom)
        self.full_range = QPushButton("FULL RANGE")
        self.full_range.setToolTip("Restore Start/End to the full loaded recording.")
        self.full_range.clicked.connect(self.use_full_range)
        range_grid.addWidget(self.apply_range, 3, 0, 1, 2)
        range_grid.addWidget(self.use_zoom, 4, 0)
        range_grid.addWidget(self.full_range, 4, 1)
        self.range_summary = QLabel("No range loaded")
        self.range_summary.setObjectName("subtitle")
        self.range_summary.setWordWrap(True)
        range_grid.addWidget(self.range_summary, 5, 0, 1, 2)
        self.range_panel = CollapsiblePanel("WORKING RANGE", range_group, expanded=True)
        control_layout.addWidget(self.range_panel)

        detection_group = QGroupBox("")
        detection_form = QFormLayout(detection_group)
        detection_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        detection_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.event_label = QLineEdit()
        self.event_label.setPlaceholderText("e.g. Passive_wrist_extension")
        self.direction = QComboBox()
        self.direction.addItem("Maximum (top)", "maxima")
        self.direction.addItem("Minimum (bottom)", "minima")
        self.direction.addItem("Both", "both")
        self.direction.setCurrentIndex(0)
        self.direction.setToolTip("Maximum finds the TOP of the trace. Minimum finds the BOTTOM. Both finds both kinds.")
        self.auto_prominence = QCheckBox("Auto prominence")
        self.auto_prominence.setChecked(True)
        self.prominence = QDoubleSpinBox()
        self.prominence.setRange(0, 1_000_000)
        self.prominence.setDecimals(3)
        self.prominence.setValue(5.0)
        self.prominence.setEnabled(False)
        self.distance = QSpinBox()
        self.distance.setRange(1, 1_000_000)
        self.distance.setValue(20)
        self.width = QDoubleSpinBox()
        self.width.setRange(0, 1_000_000)
        self.width.setDecimals(2)
        self.width.setValue(0.0)
        detection_form.addRow("Event label", self.event_label)
        detection_form.addRow("Peak mode", self.direction)
        peak_mode_hint = QLabel("Maximum = top of trace   •   Minimum = bottom")
        peak_mode_hint.setObjectName("subtitle")
        peak_mode_hint.setWordWrap(True)
        detection_form.addRow(peak_mode_hint)
        detection_form.addRow(self.auto_prominence)
        detection_form.addRow("Prominence", self.prominence)
        detection_form.addRow("Min distance", self.distance)
        detection_form.addRow("Min width (0=off)", self.width)
        self.detect_button = QPushButton("FIND PEAKS")
        self.detect_button.setObjectName("peakButton")
        self.detect_button.setToolTip(
            "Run scipy.signal.find_peaks on the primary axis in the current range. Results go directly into the table."
        )
        self.detect_button.clicked.connect(self.detect_peaks)
        detection_form.addRow(self.detect_button)
        confirm_row = QWidget()
        confirm_layout = QHBoxLayout(confirm_row)
        confirm_layout.setContentsMargins(0, 0, 0, 0)
        self.confirm_range = QPushButton("✓ CONFIRM RANGE + CONTINUE")
        self.confirm_range.setObjectName("accentButton")
        self.confirm_range.setToolTip("Lock the current range's reviewed peaks into the working dataset, return to the full graph, and continue with another range.")
        self.confirm_range.clicked.connect(self.confirm_current_range)
        self.discard_range = QPushButton("DISCARD DRAFT")
        self.discard_range.setToolTip("Remove only unconfirmed peaks created for the current bodypart/axis/range.")
        self.discard_range.clicked.connect(self.discard_current_draft)
        confirm_layout.addWidget(self.confirm_range, 1)
        confirm_layout.addWidget(self.discard_range)
        detection_form.addRow(confirm_row)
        self.draft_status = QLabel("No draft range")
        self.draft_status.setObjectName("subtitle")
        self.draft_status.setWordWrap(True)
        detection_form.addRow(self.draft_status)
        history_row = QWidget()
        history_layout = QHBoxLayout(history_row)
        history_layout.setContentsMargins(0, 0, 0, 0)
        self.undo_detection = QPushButton("↶ UNDO LAST")
        self.undo_detection.setToolTip("Restore the event dataset to the state before the most recent peak-find/clear action.")
        self.undo_detection.clicked.connect(self.undo_last_peak_action)
        self.clear_axis_peaks = QPushButton("CLEAR THIS AXIS")
        self.clear_axis_peaks.setToolTip("Remove detected/manual peak rows for the current bodypart and detection axis only.")
        self.clear_axis_peaks.clicked.connect(self.clear_current_axis_peaks)
        history_layout.addWidget(self.undo_detection)
        history_layout.addWidget(self.clear_axis_peaks)
        detection_form.addRow(history_row)
        self.detection_panel = CollapsiblePanel("FIND PEAKS", detection_group, expanded=True)
        control_layout.addWidget(self.detection_panel)

        review_group = QGroupBox("")
        review_grid = QGridLayout(review_group)
        self.manual_frame = QSpinBox()
        self.manual_frame.setRange(0, 2_000_000_000)
        self.manual_add = QPushButton("ADD MANUAL FRAME")
        self.manual_add.setToolTip("Add a missed event at this frame. Clicking the graph updates this frame box.")
        self.manual_add.clicked.connect(self.add_manual_peak)
        self.move_selected = QPushButton("MOVE SELECTED PEAK")
        self.move_selected.setToolTip(
            "Reliable manual move: select one event row, enter the corrected destination in the Frame box, "
            "then press MOVE SELECTED PEAK. The event time and XYZ values update together."
        )
        self.move_selected.clicked.connect(self.toggle_move_selected)
        self.remove_selected_manual = QPushButton("REMOVE SELECTED PEAK")
        self.remove_selected_manual.setToolTip("Remove the same selected EVENT DATASET row(s) without needing to resize the table panel.")
        self.remove_selected_manual.clicked.connect(self.remove_selected_rows)
        self.move_status = QLabel("MOVE MODE: click the corrected frame on the graph")
        self.move_status.setObjectName("moveStatus")
        self.move_status.setWordWrap(True)
        self.move_status.hide()
        review_grid.addWidget(QLabel("Frame"), 0, 0)
        review_grid.addWidget(self.manual_frame, 0, 1)
        review_grid.addWidget(self.manual_add, 1, 0, 1, 2)
        review_grid.addWidget(self.move_selected, 2, 0, 1, 2)
        review_grid.addWidget(self.remove_selected_manual, 3, 0, 1, 2)
        review_grid.addWidget(self.move_status, 4, 0, 1, 2)
        self.review_panel = CollapsiblePanel("MANUAL REVIEW", review_group, expanded=True)
        control_layout.addWidget(self.review_panel)
        control_layout.addStretch(1)

        # v0.4: the controls can now be expanded freely without being crushed.
        # A dedicated vertical scroll area keeps the plot/table full-size.
        self.control_scroll = QScrollArea()
        self.control_scroll.setWidgetResizable(True)
        self.control_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.control_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.control_scroll.setMinimumWidth(325)
        self.control_scroll.setMaximumWidth(450)
        self.control_scroll.setWidget(control_panel)
        workspace.addWidget(self.control_scroll)
        self.workspace = workspace

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter = self.right_splitter

        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_header = QHBoxLayout()
        self.plot_title = QLabel("PEAK LAB")
        self.plot_title.setObjectName("plotTitle")
        self.plot_status = QLabel("Load a 3D CSV to begin")
        self.plot_status.setObjectName("subtitle")
        plot_header.addWidget(self.plot_title)
        plot_header.addStretch(1)
        self.controls_toggle = QPushButton("HIDE CONTROLS")
        self.controls_toggle.setObjectName("utilityButton")
        self.controls_toggle.setToolTip("Hide/show the left Peak Lab controls so the plot can use the full width.")
        self.controls_toggle.clicked.connect(self._toggle_controls)
        plot_header.addWidget(self.controls_toggle)
        self.moon_status = QLabel("")
        self.moon_status.setObjectName("moonStatus")
        self.moon_status.hide()
        plot_header.addWidget(self.moon_status)
        self.hand_move = QPushButton("✋  SELECT / MOVE PEAK")
        self.hand_move.setCheckable(True)
        self.hand_move.setToolTip(
            "Manual review helper. Select a peak row in EVENT DATASET, then edit the existing Frame box "
            "and press MOVE SELECTED PEAK. Plot clicks can still update the Frame box when available."
        )
        self.hand_move.toggled.connect(self._hand_move_toggled)
        plot_header.addWidget(self.hand_move)
        plot_header.addWidget(self.plot_status)
        plot_layout.addLayout(plot_header)

        if WEBENGINE_AVAILABLE:
            self.web = QWebEngineView()
            self.bridge = PlotBridge(self)
            self.bridge.selection.connect(self._selection_from_plot)
            self.bridge.clicked.connect(self._click_from_plot)
            self.bridge.zoomRange.connect(self._zoom_from_plot)
            self.bridge.peakSelected.connect(self._peak_selected_from_plot)
            self.bridge.peakMoved.connect(self._peak_dragged_from_plot)
            self.channel = QWebChannel(self.web.page())
            self.channel.registerObject("bridge", self.bridge)
            self.web.page().setWebChannel(self.channel)
            plot_layout.addWidget(self.web, 1)
        else:
            placeholder = QLabel(
                "PySide6 QtWebEngine is not available. Install the full PySide6 package to use the embedded Plotly Peak Lab."
            )
            placeholder.setWordWrap(True)
            plot_layout.addWidget(placeholder, 1)
            self.web = None
        right_splitter.addWidget(plot_panel)

        table_panel = QWidget()
        self.table_panel = table_panel
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_header = QHBoxLayout()
        table_title = QLabel("EVENT DATASET")
        table_title.setObjectName("sectionTitle")
        self.table_count = QLabel("0 events")
        self.table_count.setObjectName("subtitle")
        table_header.addWidget(table_title)
        table_header.addStretch(1)
        table_header.addWidget(self.table_count)
        table_layout.addLayout(table_header)

        self.table = QTableWidget(0, len(self.TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(self.TABLE_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setSortingEnabled(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._table_item_changed)
        self.table.itemSelectionChanged.connect(self._table_selection_changed)
        table_layout.addWidget(self.table, 1)

        table_buttons = QHBoxLayout()
        self.remove_rows = QPushButton("REMOVE SELECTED")
        self.remove_rows.setToolTip("Delete the selected event rows from the dataset.")
        self.remove_rows.clicked.connect(self.remove_selected_rows)
        self.clear_rows = QPushButton("CLEAR TABLE")
        self.clear_rows.setToolTip("Clear the full event dataset for this session.")
        self.clear_rows.clicked.connect(self.clear_table)
        self.confirm_kept = QPushButton("✓ CONFIRM KEPT")
        self.confirm_kept.setToolTip("Confirm all currently checked draft events so they can be exported. Manual events are confirmed automatically.")
        self.confirm_kept.clicked.connect(self.confirm_kept_drafts)
        self.export_csv = QPushButton("EXPORT KEPT CSV")
        self.export_csv.setObjectName("runButton")
        self.export_csv.setToolTip("Export only rows whose Keep checkbox is checked.")
        self.export_csv.clicked.connect(self.export_kept_csv)
        self.export_mat = QPushButton("EXPORT KEPT MAT")
        self.export_mat.setObjectName("runButton")
        self.export_mat.setToolTip("Export the kept event dataset as a MATLAB .mat struct.")
        self.export_mat.clicked.connect(self.export_kept_mat)
        table_buttons.addWidget(self.remove_rows)
        table_buttons.addWidget(self.clear_rows)
        table_buttons.addWidget(self.confirm_kept)
        table_buttons.addStretch(1)
        table_buttons.addWidget(self.export_csv)
        table_buttons.addWidget(self.export_mat)
        table_layout.addLayout(table_buttons)
        right_splitter.addWidget(table_panel)
        right_splitter.setSizes([560, 250])

        workspace.addWidget(right_splitter)
        workspace.setSizes([365, 1050])
        root.addWidget(workspace, 1)

        # ------------------------------------------------------------------
        # Connections
        # ------------------------------------------------------------------
        self.bodypart.currentTextChanged.connect(self._bodypart_changed)
        self.primary_axis.currentTextChanged.connect(self._primary_axis_changed)
        self.show_x.toggled.connect(lambda checked: self._trace_toggled("x", checked))
        self.show_y.toggled.connect(lambda checked: self._trace_toggled("y", checked))
        self.show_z.toggled.connect(lambda checked: self._trace_toggled("z", checked))
        self.trace_layout_mode.currentIndexChanged.connect(lambda _: self.render_plot() if self.df is not None else None)
        self.trace_palette.currentIndexChanged.connect(lambda _: self.render_plot() if self.df is not None else None)
        self.hover_details.toggled.connect(lambda _: self.render_plot())
        self.overview_slider.toggled.connect(lambda _: self.render_plot())
        self.range_start.valueChanged.connect(lambda _: self._update_range_summary())
        self.range_end.valueChanged.connect(lambda _: self._update_range_summary())
        self.auto_prominence.toggled.connect(lambda checked: self.prominence.setEnabled(not checked))
        self.fill_short_gaps.toggled.connect(lambda _: self._update_cleanup_note())
        self.max_gap.valueChanged.connect(lambda _: self._update_cleanup_note())
        self.smoothing.currentIndexChanged.connect(lambda _: self._update_cleanup_note())
        self.savgol_window.valueChanged.connect(lambda _: self._update_cleanup_note())
        self.savgol_poly.valueChanged.connect(lambda _: self._update_cleanup_note())
        self.butter_cutoff.valueChanged.connect(lambda _: self._update_cleanup_note())
        self.butter_order.valueChanged.connect(lambda _: self._update_cleanup_note())
        self.show_raw_reference.toggled.connect(lambda _: self.render_plot() if self.df is not None else None)
        self.cleanup_apply.clicked.connect(self.render_plot)
        self._update_cleanup_note()

    def _toggle_controls(self):
        visible = not self.control_scroll.isVisible()
        self.control_scroll.setVisible(visible)
        self.controls_toggle.setText("HIDE CONTROLS" if visible else "SHOW CONTROLS")
        if visible:
            self.workspace.setSizes([365, max(700, self.workspace.width() - 365)])
        else:
            self.workspace.setSizes([0, max(900, self.workspace.width())])
        if self.web is not None:
            self.web.page().runJavaScript("setTimeout(function(){ if(window.Plotly){ var p=document.getElementById('peakPlot'); if(p) Plotly.Plots.resize(p); } }, 0);")

    # ----------------------------------------------------------------------
    # Public theme hook
    # ----------------------------------------------------------------------
    def set_theme(self, theme: str):
        self.theme = theme if theme in {"dark", "light"} else "dark"
        if self.df is not None:
            self.render_plot()

    def _cleanup_changed(self):
        self._update_cleanup_note()
        if self.df is not None:
            self.render_plot()

    def _update_cleanup_note(self):
        mode = self.smoothing.currentData() if hasattr(self, "smoothing") else "none"
        if mode == "savgol":
            text = (
                "Savitzky–Golay: preserves peak shape/timing well and is useful for smooth kinematic curves. "
                "Tradeoff: the window/polyorder need tuning, sharp outliers can create ringing/overshoot, and it is not ideal across long gaps."
            )
        elif mode == "butter":
            text = (
                "Butterworth: strong low-pass suppression with an interpretable cutoff frequency. Peak timing is protected with zero-phase filtering. "
                "Tradeoff: it can round/attenuate fast peaks, needs a valid sampling rate/cutoff, and is applied separately across long gaps."
            )
        else:
            text = "No smoothing: Peak Lab uses the loaded coordinates directly. Short-gap filling can still be enabled independently."
        if hasattr(self, "fill_short_gaps") and self.fill_short_gaps.isChecked():
            text += f" Short-gap fill is ON for bounded gaps ≤ {self.max_gap.value()} frame(s); longer gaps remain NaN."
        self.cleanup_note.setText(text)

    def _sampling_rate(self, subset: pd.DataFrame) -> float:
        if "time_seconds" in subset.columns:
            t = pd.to_numeric(subset["time_seconds"], errors="coerce").to_numpy(dtype=float)
            dt = np.diff(t[np.isfinite(t)])
            dt = dt[np.isfinite(dt) & (dt > 0)]
            if dt.size:
                return float(1.0 / np.median(dt))
        return 60.0

    def _processed_values(self, subset: pd.DataFrame, bp: str, axis: str) -> tuple[np.ndarray, np.ndarray]:
        raw = pd.to_numeric(subset[f"{bp}_{axis}"], errors="coerce").to_numpy(dtype=float)
        values = raw.copy()
        filled_mask = np.zeros(values.shape, dtype=bool)
        if self.fill_short_gaps.isChecked():
            values, filled_mask = fill_short_internal_gaps(values, self.max_gap.value())
        mode = self.smoothing.currentData() or "none"
        if mode == "savgol":
            window = int(self.savgol_window.value())
            if window % 2 == 0:
                window += 1
            values = savgol_finite_segments(values, window=window, polyorder=self.savgol_poly.value())
        elif mode == "butter":
            values = butterworth_finite_segments(
                values,
                fs=self._sampling_rate(subset),
                cutoff_hz=self.butter_cutoff.value(),
                order=self.butter_order.value(),
            )
        return values, filled_mask

    # ----------------------------------------------------------------------
    # Data loading / signal selection
    # ----------------------------------------------------------------------
    def load_csv(self):
        path = Path(self.csv_path.text())
        if not path.is_file():
            QMessageBox.warning(self, "CSV not found", "Select an existing triangulated 3D CSV file.")
            return
        try:
            df = pd.read_csv(path)
            if "frame" not in df.columns:
                raise KeyError("The CSV must contain a frame column.")
            bodyparts = infer_bodyparts(df.columns)
            if not bodyparts:
                raise KeyError("No bodyparts with complete _x, _y, _z columns were found.")
            for col in [c for c in df.columns if re.match(r"^.+_[xyz]$", str(c))]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["frame"] = pd.to_numeric(df["frame"], errors="raise").astype(int)
            # v0.5.6: derive per-frame 3D speed for each bodypart so exported
            # peak/timepoint rows include the movement rate at that exact frame.
            if "time_seconds" in df.columns:
                time_values = pd.to_numeric(df["time_seconds"], errors="coerce").to_numpy(dtype=float)
            else:
                time_values = np.arange(len(df), dtype=float) / 60.0
            for bp in bodyparts:
                xyz = df[[f"{bp}_x", f"{bp}_y", f"{bp}_z"]].to_numpy(dtype=float)
                speed = np.full(len(df), np.nan, dtype=float)
                if len(df) > 1:
                    delta = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
                    dt = np.diff(time_values)
                    good = np.isfinite(delta) & np.isfinite(dt) & (dt > 0)
                    speed[np.flatnonzero(good) + 1] = delta[good] / dt[good]
                df[f"{bp}_velocity_3d"] = speed
            source_changed = self.source_path is not None and self.source_path.resolve() != path.resolve()
            self.df = df
            self.source_path = path
            if source_changed:
                self.session_rows.clear()
                self._refresh_table()
            # A fresh source starts in the intuitive top-peak mode. Saved sessions
            # can still restore minimum/both immediately after loading.
            self.direction.setCurrentIndex(0)
            self.bodypart.blockSignals(True)
            self.bodypart.clear()
            self.bodypart.addItems(bodyparts)
            self.bodypart.blockSignals(False)
            self._full_start = int(df["frame"].min())
            self._full_end = int(df["frame"].max())
            self.range_start.setValue(self._full_start)
            self.range_end.setValue(self._full_end)
            self.manual_frame.setRange(self._full_start, self._full_end)
            self.range_start.setRange(self._full_start, self._full_end)
            self.range_end.setRange(self._full_start, self._full_end)
            self._suggest_label(force=True)
            self._selected_peak_uid = None
            self._last_zoom = None
            self._history.clear()
            self._update_range_summary()
            # Loading and plotting are deliberately separated. A rendering problem must
            # never make a valid CSV look as if it failed to load.
            self._update_context_bar()
            self.sourceLoaded.emit(str(path))
            self.message.emit(f"Loaded peak source: {path.name} | bodyparts={bodyparts}")
        except Exception as exc:
            QMessageBox.critical(self, "Could not load CSV", str(exc))
            return

        try:
            self.render_plot()
        except Exception as exc:
            self.message.emit(f"Peak source loaded, but plot rendering reported: {exc}")

    def _primary_axis_key(self) -> str | None:
        text = self.primary_axis.currentText().strip().lower()
        return text if text in {"x", "y", "z"} else None

    def _bodypart_changed(self, _text: str):
        self._cancel_move_mode()
        self._update_context_bar()
        self._suggest_label()
        if self.df is not None:
            self.render_plot()

    def _primary_axis_changed(self, axis: str):
        self._update_context_bar()
        # "None" is a view-only state: all visible traces remain equal and peak
        # detection/manual addition is disabled until X, Y, or Z is chosen again.
        axis_key = axis.strip().lower()
        axis_checkbox = {"x": self.show_x, "y": self.show_y, "z": self.show_z}.get(axis_key)
        if axis_checkbox is not None and not axis_checkbox.isChecked():
            axis_checkbox.blockSignals(True)
            axis_checkbox.setChecked(True)
            axis_checkbox.blockSignals(False)
        self._cancel_move_mode()
        if self.df is not None:
            self.render_plot()

    def _trace_toggled(self, axis: str, checked: bool):
        """Visible traces are independent from the optional detection axis."""
        current = self._primary_axis_key()
        if not checked and current == axis:
            self.primary_axis.setCurrentText("None")
            return
        if self.df is not None:
            self.render_plot()

    def _update_context_bar(self):
        if not hasattr(self, "context_bar"):
            return
        source = self.source_path.name if self.source_path else "—"
        bp = self.bodypart.currentText() or "—"
        axis = (self._primary_axis_key() or "None").upper()
        confirmed = sum(1 for row in self.session_rows if bool(row.get("_confirmed", True)) and row.get("keep", True))
        self.context_bar.setText(f"Source: {source}  •  Bodypart: {bp}  •  Primary: {axis}  •  Review: {confirmed}/{len(self.session_rows)} confirmed")

    def _set_busy(self, text: str = "", phase: int = 0):
        phases = ["🌑", "🌓", "🌕", "🌗"]
        if text:
            self.moon_status.setText(f"{phases[phase % len(phases)]}  {text} …")
            self.moon_status.show()
            if not self._busy_cursor_set:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                self._busy_cursor_set = True
            QApplication.processEvents()
        else:
            self.moon_status.hide()
            if self._busy_cursor_set:
                QApplication.restoreOverrideCursor()
                self._busy_cursor_set = False
            QApplication.processEvents()

    def _push_history(self, action: str):
        self._history.append((action, copy.deepcopy(self.session_rows)))
        if len(self._history) > 20:
            self._history.pop(0)

    def undo_last_peak_action(self):
        if not self._history:
            QMessageBox.information(self, "Nothing to undo", "No Peak Lab detection/clear action is available to undo.")
            return
        action, rows = self._history.pop()
        self.session_rows = rows
        self._selected_peak_uid = None
        self._refresh_table()
        self.render_plot()
        self.message.emit(f"Undid Peak Lab action: {action}")

    def clear_current_axis_peaks(self):
        if self.df is None:
            return
        bp = self.bodypart.currentText()
        axis = self._primary_axis_key()
        if axis is None:
            QMessageBox.information(self, "Choose a primary axis", "Choose X, Y, or Z before clearing peaks for one axis.")
            return
        matches = [r for r in self.session_rows if r.get("bodypart") == bp and r.get("primary_axis") == axis]
        if not matches:
            return
        result = QMessageBox.question(
            self, "Clear current signal peaks?",
            f"Remove {len(matches)} event row(s) for {bp}/{axis.upper()} only?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._push_history(f"clear {bp}/{axis}")
        self.session_rows = [r for r in self.session_rows if not (r.get("bodypart") == bp and r.get("primary_axis") == axis)]
        self._selected_peak_uid = None
        self._refresh_table()
        self.render_plot()

    def _suggest_label(self, force: bool = False):
        bp = self.bodypart.currentText().strip()
        if not bp:
            return
        current = self.event_label.text().strip()
        new_label = f"Passive_{bp}_movement"
        if force or not current or current == self._auto_label:
            self.event_label.setText(new_label)
            self._auto_label = new_label

    # ----------------------------------------------------------------------
    # Range interaction
    # ----------------------------------------------------------------------
    def use_full_range(self):
        if self.df is None:
            return
        self.range_start.setValue(self._full_start)
        self.range_end.setValue(self._full_end)
        self._last_zoom = None
        self.pick_range.setChecked(False)
        self._update_range_summary()
        self.render_plot()

    def use_current_zoom(self):
        if self.df is None:
            return
        if self._last_zoom is None:
            QMessageBox.information(self, "No zoom window", "Zoom the Plotly graph first, then press USE CURRENT ZOOM.")
            return
        xmin, xmax = self._last_zoom
        start = max(self._full_start, int(round(min(xmin, xmax))))
        end = min(self._full_end, int(round(max(xmin, xmax))))
        self.range_start.setValue(start)
        self.range_end.setValue(end)
        self._update_range_summary()
        self.render_plot()
        self.message.emit(f"Current Plotly zoom -> working range {start}-{end}")

    def _zoom_from_plot(self, xmin: float, xmax: float):
        self._last_zoom = (float(xmin), float(xmax))

    def _update_range_summary(self):
        if self.df is None:
            self.range_summary.setText("No range loaded")
            return
        start, end = sorted((self.range_start.value(), self.range_end.value()))
        axis = self._primary_axis_key()
        peak_count = sum(
            1 for row in self.session_rows
            if row.get("keep", True)
            and row.get("bodypart") == self.bodypart.currentText()
            and (axis is None or row.get("primary_axis") == axis)
            and start <= int(row.get("frame", -1)) <= end
        )
        time_text = ""
        if "time_seconds" in self.df.columns:
            try:
                first = self._row_for_frame(start)
                last = self._row_for_frame(end)
                t0 = float(first.get("time_seconds", np.nan))
                t1 = float(last.get("time_seconds", np.nan))
                if np.isfinite(t0) and np.isfinite(t1):
                    time_text = f" • {t0:.3f}–{t1:.3f} s • duration {max(0.0, t1-t0):.3f} s"
            except Exception:
                pass
        self.range_summary.setText(f"Frames {start:,}–{end:,}{time_text} • {peak_count} kept peak(s)")
        self._update_draft_status()

    def _range_mode_toggled(self, checked: bool):
        self.pick_range.setText("CANCEL RANGE PICK" if checked else "SELECT RANGE ON PLOT")
        if self.web is not None:
            mode = "select" if checked else "zoom"
            self.web.page().runJavaScript(
                f"var p=document.getElementById('peakPlot'); if(p && window.Plotly) Plotly.relayout(p, {{dragmode:'{mode}'}});"
            )

    def _selection_from_plot(self, xmin: float, xmax: float):
        if self.df is None:
            return
        start = max(self._full_start, int(round(min(xmin, xmax))))
        end = min(self._full_end, int(round(max(xmin, xmax))))
        self.range_start.setValue(start)
        self.range_end.setValue(end)
        self.pick_range.blockSignals(True)
        self.pick_range.setChecked(False)
        self.pick_range.blockSignals(False)
        self.pick_range.setText("SELECT RANGE ON PLOT")
        self._update_range_summary()
        self.message.emit(f"Plot selection -> frames {start} to {end}")
        self.render_plot()

    def _click_from_plot(self, x: float):
        frame = self._nearest_frame(int(round(x)))
        self.last_clicked_frame = frame
        self.manual_frame.setValue(frame)
        # v0.5.4: plot clicks are optional helpers only. They update the existing
        # Frame box, but event movement is committed from the selected table row +
        # Frame box so manual review does not depend on fragile WebEngine hit tests.
        if self.hand_move.isChecked():
            rows = self._selected_event_row_indices()
            if len(rows) == 1:
                self.move_status.setText(
                    f"Destination frame set to {frame}. Press MOVE SELECTED PEAK to commit."
                )
                self.move_status.show()
                self.message.emit(
                    f"Manual move destination -> frame {frame}. Press MOVE SELECTED PEAK to commit."
                )
                return
        self.message.emit(f"Plot click -> frame {frame}. Use ADD MANUAL FRAME if this should be an event.")

    def _hand_move_toggled(self, checked: bool):
        """Keep the classic hand control without depending on Plotly marker clicks.

        The visual placement is unchanged from v0.5.2. When enabled it guides the
        user into the deterministic row + Frame-box workflow.
        """
        if checked:
            # Move mode should be one click: peak hit-testing is most reliable when
            # Plotly hover/click details are active, so restore Hover details
            # automatically instead of asking the user to enable two controls.
            if not self.hover_details.isChecked():
                self.hover_details.blockSignals(True)
                self.hover_details.setChecked(True)
                self.hover_details.blockSignals(False)
            self.hand_move.setText("✋  MOVE MODE ON — SELECT PEAK + FRAME")
            # Open the already-existing Manual Review panel; no widgets are added.
            try:
                self.review_panel.toggle.setChecked(True)
                self.review_panel._apply_state(True)
            except Exception:
                pass
            rows = self._selected_event_row_indices()
            if len(rows) == 1 and 0 <= rows[0] < len(self.session_rows):
                record = self.session_rows[rows[0]]
                self._selected_peak_uid = str(record.get("_uid", "")) or None
                self.manual_frame.setValue(int(record.get("frame", self.manual_frame.value())))
                self.move_status.setText(
                    "Edit Frame on the left, then press MOVE SELECTED PEAK. Time + XYZ update together."
                )
                self.move_status.show()
                self.manual_frame.setFocus()
                self.manual_frame.selectAll()
                self.message.emit(
                    "Manual move: selected row loaded into the Frame box. Type the corrected frame and press MOVE SELECTED PEAK."
                )
            else:
                self.move_status.setText(
                    "Click a peak on the graph (or select one EVENT DATASET row); its frame will appear in MANUAL REVIEW."
                )
                self.move_status.show()
                self.message.emit(
                    "Manual move: click one peak first, then choose the destination frame and press MOVE SELECTED PEAK."
                )
        else:
            self.hand_move.setText("✋  SELECT / MOVE PEAK")
            self._move_row = None
            self.move_status.hide()
        self.render_plot()

    def _peak_selected_from_plot(self, uid: str):
        for row_index, record in enumerate(self.session_rows):
            if str(record.get("_uid", "")) != uid:
                continue
            self._selected_peak_uid = uid
            self.table.clearSelection()
            self.table.selectRow(row_index)
            item = self.table.item(row_index, 0)
            if item is not None:
                self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.manual_frame.setValue(int(record.get("frame", self.manual_frame.value())))
            if self.hand_move.isChecked():
                self.move_status.setText(
                    "Peak selected. Edit Frame on the left, then press MOVE SELECTED PEAK."
                )
                self.move_status.show()
                self.message.emit(
                    f"Selected event at frame {record.get('frame')}. Enter the corrected Frame and press MOVE SELECTED PEAK."
                )
            else:
                self.message.emit(f"Selected peak at frame {record.get('frame')}.")
            self._update_selected_peak_highlight()
            return

    def _peak_dragged_from_plot(self, uid: str, x: float):
        for row_index, record in enumerate(self.session_rows):
            if str(record.get("_uid", "")) == uid:
                frame = self._nearest_frame(int(round(x)))
                self._selected_peak_uid = uid
                self._move_event_to_frame(row_index, frame)
                self.message.emit(f"Dragged peak -> frame {frame}")
                return

    def _frame_subset(self) -> pd.DataFrame:
        assert self.df is not None
        start, end = sorted((self.range_start.value(), self.range_end.value()))
        subset = self.df[(self.df["frame"] >= start) & (self.df["frame"] <= end)].copy()
        if subset.empty:
            raise ValueError("The selected frame range contains no data.")
        return subset

    # ----------------------------------------------------------------------
    # Plot rendering
    # ----------------------------------------------------------------------
    def render_plot(self):
        if self.df is None or self.web is None:
            return
        try:
            subset = self._frame_subset()
            bp = self.bodypart.currentText()
            axis_primary = self._primary_axis_key()
            if not bp:
                return

            trace_palette_key = str(self.trace_palette.currentData() or "coral_grove")
            palette = plot_palette(self.theme, trace_palette_key)
            visibility = {"x": self.show_x.isChecked(), "y": self.show_y.isChecked(), "z": self.show_z.isChecked()}
            if not any(visibility.values()):
                visibility["z"] = True
            visible_axes = [axis for axis in ("x", "y", "z") if visibility[axis]]

            layout_mode = str(self.trace_layout_mode.currentData() or "overlay")
            # Only Separate XYZ creates multiple plot panels. Primary trace on top
            # deliberately keeps the original single-canvas Peak Lab look.
            stacked = layout_mode == "separate" and len(visible_axes) > 1
            axis_order = visible_axes[:]
            render_axes = visible_axes[:]
            if layout_mode == "primary_top" and axis_primary in visible_axes:
                # Plot the primary signal last so it literally sits above the
                # other traces, while preserving one shared coordinate canvas.
                render_axes = [axis for axis in visible_axes if axis != axis_primary] + [axis_primary]

            if stacked:
                nrows = len(axis_order)
                row_heights = [1.0 / nrows] * nrows
                fig = make_subplots(
                    rows=nrows,
                    cols=1,
                    shared_xaxes=True,
                    vertical_spacing=min(0.045, 0.14 / max(nrows, 1)),
                    row_heights=row_heights,
                )
                axis_row = {axis: idx + 1 for idx, axis in enumerate(axis_order)}
            else:
                fig = go.Figure()
                axis_row = {axis: None for axis in visible_axes}

            def add_trace(trace, axis: str):
                row = axis_row.get(axis)
                if stacked and row is not None:
                    fig.add_trace(trace, row=row, col=1)
                else:
                    fig.add_trace(trace)

            processed_by_axis: dict[str, dict[int, float]] = {}
            cleanup_active = self.fill_short_gaps.isChecked() or (self.smoothing.currentData() or "none") != "none"
            for axis in render_axes:
                col = f"{bp}_{axis}"
                processed, filled_mask = self._processed_values(subset, bp, axis)
                raw_values = pd.to_numeric(subset[col], errors="coerce").to_numpy(dtype=float)
                xyz = np.column_stack(
                    [
                        subset["frame"].to_numpy(),
                        subset.get("time_seconds", pd.Series(np.nan, index=subset.index)).to_numpy(),
                        subset.get("timestamp", pd.Series("", index=subset.index)).astype(str).to_numpy(),
                        subset[f"{bp}_x"].to_numpy(),
                        subset[f"{bp}_y"].to_numpy(),
                        subset[f"{bp}_z"].to_numpy(),
                        processed,
                        filled_mask.astype(int),
                    ]
                )
                hovertemplate = None
                hoverinfo = "skip"
                if self.hover_details.isChecked():
                    hovertemplate = (
                        "Frame: %{customdata[0]}<br>Elapsed: %{customdata[1]:.3f} s<br>"
                        "Timestamp: %{customdata[2]}<br>X: %{customdata[3]:.3f}<br>"
                        "Y: %{customdata[4]:.3f}<br>Z: %{customdata[5]:.3f}<br>"
                        "Displayed: %{customdata[6]:.3f}<br>Gap-filled: %{customdata[7]}<extra></extra>"
                    )
                    hoverinfo = None
                processed_by_axis[axis] = {
                    int(frame): float(value) if np.isfinite(value) else np.nan
                    for frame, value in zip(subset["frame"].to_numpy(dtype=int), processed)
                }
                if cleanup_active and axis_primary == axis and self.show_raw_reference.isChecked():
                    add_trace(
                        go.Scattergl(
                            x=subset["frame"], y=raw_values, mode="lines", name=f"{axis.upper()} raw",
                            connectgaps=False, line=dict(color=palette[axis], width=1.0, dash="dot"),
                            opacity=0.35, hoverinfo="skip", showlegend=not stacked,
                        ),
                        axis,
                    )
                add_trace(
                    go.Scattergl(
                        x=subset["frame"], y=processed, customdata=xyz, mode="lines",
                        name=axis.upper() + (" cleaned" if cleanup_active else ""), connectgaps=False,
                        line=dict(color=palette[axis], width=2.4 if axis_primary == axis else 1.45),
                        opacity=1.0 if axis_primary == axis else 0.82,
                        hovertemplate=hovertemplate, hoverinfo=hoverinfo,
                        showlegend=not stacked,
                    ),
                    axis,
                )

            marker_groups = {
                axis: {"x": [], "y": [], "custom": [], "colors": [], "symbols": [], "sizes": [], "opacities": []}
                for axis in visible_axes
            }
            start_frame, end_frame = sorted((self.range_start.value(), self.range_end.value()))
            self._sync_keep_from_table()
            for record in self.session_rows:
                if not record.get("keep", True) or record.get("bodypart") != bp:
                    continue
                record_axis = str(record.get("primary_axis", "")).lower()
                if record_axis not in marker_groups:
                    continue
                if axis_primary is not None and record_axis != axis_primary and layout_mode in {"overlay", "primary_top"}:
                    continue
                frame = int(record.get("frame", -1))
                if frame < start_frame or frame > end_frame:
                    continue
                value = processed_by_axis.get(record_axis, {}).get(frame, np.nan)
                if not np.isfinite(value):
                    continue
                value = float(value)
                record["primary_value"] = value
                peak_kind = str(record.get("_peak_kind", "maximum"))
                confirmed = bool(record.get("_confirmed", True))
                selected = str(record.get("_uid", "")) == str(self._selected_peak_uid or "")
                group = marker_groups[record_axis]
                group["x"].append(frame)
                group["y"].append(value)
                group["custom"].append([
                    record.get("event_index", ""), record.get("event_label", ""),
                    record.get("time_seconds", np.nan), record.get("timestamp", ""),
                    peak_kind, str(record.get("_uid", "")), "Confirmed" if confirmed else "Draft",
                    record_axis.upper(), record.get("velocity_3d", np.nan),
                ])
                group["sizes"].append(20 if selected else (13 if not confirmed else 10))
                group["opacities"].append(1.0 if confirmed or selected else 0.70)
                if peak_kind == "minimum":
                    group["colors"].append(palette["peak_min"]); group["symbols"].append("triangle-down")
                elif peak_kind == "manual":
                    group["colors"].append(palette["peak_manual"]); group["symbols"].append("diamond")
                else:
                    group["colors"].append(palette["peak_max"]); group["symbols"].append("circle")

            marker_uids: list[str] = []
            active_events = 0
            for axis in visible_axes:
                group = marker_groups[axis]
                if not group["x"]:
                    continue
                active_events += len(group["x"])
                marker_uids.extend([str(row[5]) for row in group["custom"]])
                peak_hover = None
                peak_hoverinfo = "skip"
                if self.hover_details.isChecked():
                    peak_hover = (
                        "Event %{customdata[0]}<br>%{customdata[1]}<br>Frame: %{x}<br>"
                        "Elapsed: %{customdata[2]:.3f} s<br>Timestamp: %{customdata[3]}<br>"
                        "Axis: %{customdata[7]}<br>Mode: %{customdata[4]}<br>Status: %{customdata[6]}<br>"
                        "Value: %{y:.3f}<br>3D velocity: %{customdata[8]:.3f}<extra></extra>"
                    )
                    peak_hoverinfo = None
                add_trace(
                    go.Scatter(
                        x=group["x"], y=group["y"], customdata=np.asarray(group["custom"], dtype=object),
                        mode="markers", name="Peaks",
                        marker=dict(color=group["colors"], symbol=group["symbols"], size=group["sizes"],
                                    opacity=group["opacities"], line=dict(color=palette["peak_outline"], width=1.4)),
                        hovertemplate=peak_hover, hoverinfo=peak_hoverinfo, showlegend=False,
                    ),
                    axis,
                )

            common_layout = dict(
                autosize=True,
                paper_bgcolor=palette["paper"], plot_bgcolor=palette["plot"],
                font=dict(color=palette["text"], family="Courier New"),
                dragmode="select" if self.pick_range.isChecked() else (False if self.hand_move.isChecked() else "zoom"),
                hovermode=("closest" if self.hand_move.isChecked() else "x unified") if self.hover_details.isChecked() else False,
                margin=dict(l=68, r=18, t=42, b=58),
                uirevision=f"{bp}-{axis_primary or 'all'}-{start_frame}-{end_frame}-{self.theme}-{layout_mode}-{trace_palette_key}",
            )
            if stacked:
                common_layout["showlegend"] = False
                common_layout["autosize"] = True
            else:
                common_layout["legend"] = dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)")
            fig.update_layout(**common_layout)

            grid_kwargs = dict(
                showspikes=self.hover_details.isChecked(), gridcolor=palette["grid"],
                zerolinecolor=palette["grid"], automargin=True,
            )
            if stacked:
                for row_index, axis in enumerate(axis_order, start=1):
                    fig.update_yaxes(title_text=axis.upper(), row=row_index, col=1, **grid_kwargs)
                    fig.update_xaxes(row=row_index, col=1, **grid_kwargs)
                fig.update_xaxes(title_text="Frame", row=len(axis_order), col=1)
                fig.update_xaxes(rangeslider_visible=self.overview_slider.isChecked(), row=len(axis_order), col=1)
            else:
                fig.update_xaxes(title_text="Frame", rangeslider_visible=self.overview_slider.isChecked(), **grid_kwargs)
                fig.update_yaxes(title_text=f"{bp} 3D coordinate", **grid_kwargs)

            if self._last_zoom is not None:
                z0, z1 = sorted(self._last_zoom)
                left = max(float(start_frame), float(z0))
                right = min(float(end_frame), float(z1))
                if np.isfinite(left) and np.isfinite(right) and right > left:
                    if stacked:
                        for row_index in range(1, len(axis_order) + 1):
                            fig.update_xaxes(range=[left, right], row=row_index, col=1)
                    else:
                        fig.update_xaxes(range=[left, right])

            config = {
                "displaylogo": False, "scrollZoom": True, "responsive": True,
                "modeBarButtonsToRemove": ["lasso2d", "autoScale2d", "toggleSpikelines", "hoverCompareCartesian", "hoverClosestCartesian"],
            }
            if self._plotly_js_path is None:
                cache_dir = Path(tempfile.gettempdir()) / "motion_pipeline_gui"
                cache_dir.mkdir(parents=True, exist_ok=True)
                js_path = cache_dir / "plotly.min.js"
                if not js_path.is_file():
                    js_path.write_text(get_plotlyjs(), encoding="utf-8")
                self._plotly_js_path = js_path

            html = fig.to_html(include_plotlyjs=False, full_html=True, div_id="peakPlot", config=config)
            fill_css = "<style>html,body,#peakPlot{width:100%;height:100%;margin:0;padding:0;overflow:hidden;} body>div{height:100% !important;}</style>"
            resize_js = "<script>window.addEventListener('resize',function(){var p=document.getElementById('peakPlot');if(p&&window.Plotly){Plotly.Plots.resize(p);}});</script>"
            html = html.replace("</head>", f'<script src="{self._plotly_js_path.resolve().as_uri()}"></script>{fill_css}{resize_js}</head>')
            peak_uids_json = json.dumps(marker_uids)
            bridge_js = f'''
<script type="text/javascript" src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script type="text/javascript">
window.motionPeakUids = {peak_uids_json};
new QWebChannel(qt.webChannelTransport, function(channel) {{
  window.bridge = channel.objects.bridge;
  var plot = document.getElementById('peakPlot');
  plot.on('plotly_selected', function(data) {{
    if (!data) return;
    if (data.range && data.range.x && data.range.x.length === 2) {{
      window.bridge.receiveSelection(JSON.stringify({{xmin:Number(data.range.x[0]), xmax:Number(data.range.x[1])}})); return;
    }}
    if (!data.points || data.points.length === 0) return;
    var xs = data.points.map(function(p){{ return Number(p.x); }}).filter(Number.isFinite);
    if (xs.length) window.bridge.receiveSelection(JSON.stringify({{xmin:Math.min.apply(null,xs), xmax:Math.max.apply(null,xs)}}));
  }});
  plot.on('plotly_relayout', function(data) {{
    var a, b;
    Object.keys(data || {{}}).forEach(function(key) {{
      if (/^xaxis\\d*\\.range\\[0\\]$/.test(key)) {{
        var mate = key.replace('range[0]', 'range[1]');
        if (data[mate] !== undefined) {{ a = data[key]; b = data[mate]; }}
      }}
    }});
    if (a !== undefined && b !== undefined) {{
      window.bridge.receiveZoom(JSON.stringify({{xmin:Number(a), xmax:Number(b)}}));
    }}
  }});
  plot.on('plotly_click', function(data) {{
    if (!data || !data.points || data.points.length === 0) return;
    var pt = data.points[0];
    if (pt.data && pt.data.name === 'Peaks' && pt.customdata && pt.customdata.length > 5) {{
      window.bridge.receivePeak(JSON.stringify({{uid:String(pt.customdata[5])}})); return;
    }}
    window.bridge.receiveClick(JSON.stringify({{x:Number(pt.x)}}));
  }});
  function attachPeakDrag() {{
    var nodes = Array.from(plot.querySelectorAll('.scatterlayer .point'));
    if (!nodes.length || !window.motionPeakUids.length) return;
    var peakNodes = nodes.slice(-window.motionPeakUids.length);
    peakNodes.forEach(function(node, i) {{
      if (node.dataset.motionDragBound === '1') return;
      node.dataset.motionDragBound = '1'; node.style.cursor = 'grab';
      node.addEventListener('pointerdown', function(ev) {{
        ev.preventDefault(); ev.stopPropagation(); node.setPointerCapture(ev.pointerId); node.style.cursor = 'grabbing';
        var moved=false, startX=ev.clientX;
        function onMove(e) {{ if (Math.abs(e.clientX-startX)>3) moved=true; }}
        function onUp(e) {{
          node.style.cursor='grab'; node.removeEventListener('pointermove',onMove); node.removeEventListener('pointerup',onUp);
          if(!moved) return;
          var rect=plot.getBoundingClientRect(); var xa=plot._fullLayout && plot._fullLayout.xaxis;
          if(!xa || !xa.p2d) return;
          var pixel=e.clientX-rect.left-xa._offset; var xval=xa.p2d(pixel);
          if(Number.isFinite(Number(xval))) window.bridge.receivePeakMove(JSON.stringify({{uid:String(window.motionPeakUids[i]),x:Number(xval)}}));
        }}
        node.addEventListener('pointermove',onMove); node.addEventListener('pointerup',onUp);
      }});
    }});
  }}
  attachPeakDrag(); plot.on('plotly_afterplot', attachPeakDrag);
}});
</script>
'''
            html = html.replace("</body>", bridge_js + "</body>")
            if self._html_path:
                try:
                    self._html_path.unlink(missing_ok=True)
                except Exception:
                    pass
            fd = tempfile.NamedTemporaryFile(mode="w", suffix=".html", prefix="motion_peak_", delete=False, encoding="utf-8")
            with fd:
                fd.write(html)
            self._html_path = Path(fd.name)
            self.web.load(QUrl.fromLocalFile(str(self._html_path)))

            axis_label = axis_primary.upper() if axis_primary is not None else "ALL AXES"
            self.plot_title.setText(f"{bp}  /  {axis_label}")
            layout_label = {"overlay": "overlay", "separate": "separate XYZ", "primary_top": "primary on top"}.get(layout_mode, layout_mode)
            self.plot_status.setText(f"frames {start_frame:,}–{end_frame:,} • {active_events} kept event(s) • {layout_label}")
            self._update_range_summary()
        except Exception as exc:
            self.message.emit(f"Peak plot error: {exc}")

    # ----------------------------------------------------------------------
    # Peak detection
    # ----------------------------------------------------------------------
    def _auto_prominence(self, values: np.ndarray) -> float | None:
        finite = values[np.isfinite(values)]
        if finite.size < 3:
            return None
        q05, q95 = np.nanpercentile(finite, [5, 95])
        scale = float(q95 - q05)
        return max(scale * 0.15, np.finfo(float).eps)

    def detect_peaks(self):
        if self.df is None:
            QMessageBox.information(self, "Load data first", "Load a 3D CSV before finding peaks.")
            return
        try:
            self._set_busy("Reading working range", 0)
            subset = self._frame_subset()
            bp = self.bodypart.currentText()
            axis = self._primary_axis_key()
            if axis is None:
                QMessageBox.information(self, "Choose a primary axis", "Primary axis is set to None. Choose X, Y, or Z before running FIND PEAKS.")
                return
            col = f"{bp}_{axis}"
            values, _filled_mask = self._processed_values(subset, bp, axis)
            prominence = self._auto_prominence(values) if self.auto_prominence.isChecked() else self.prominence.value()
            if prominence is not None and self.auto_prominence.isChecked():
                self.prominence.setValue(float(prominence))
            width = self.width.value() if self.width.value() > 0 else None
            distance = self.distance.value()
            direction = self.direction.currentData() or "maxima"
            label = self.event_label.text().strip() or f"Passive_{bp}_movement"
            start, end = sorted((self.range_start.value(), self.range_end.value()))

            self._set_busy("Finding candidate peaks", 1)
            records = []
            for segment_idx in contiguous_finite_segments(values):
                segment_values = values[segment_idx]
                signals: list[tuple[str, np.ndarray]] = []
                if direction in ("maxima", "both"):
                    signals.append(("maximum", segment_values))
                if direction in ("minima", "both"):
                    signals.append(("minimum", -segment_values))
                for peak_kind, signal in signals:
                    kwargs = {"distance": distance}
                    if prominence is not None and prominence > 0:
                        kwargs["prominence"] = prominence
                    if width is not None:
                        kwargs["width"] = width
                    local_peaks, props = find_peaks(signal, **kwargs)
                    for j, local_index in enumerate(local_peaks):
                        idx = int(segment_idx[int(local_index)])
                        row = subset.iloc[idx]
                        record = self._record_from_row(
                            row,
                            bp=bp,
                            axis=axis,
                            label=label,
                            prominence=float(props.get("prominences", [np.nan] * len(local_peaks))[j]),
                            origin="auto",
                            peak_kind=peak_kind,
                            range_start=start,
                            range_end=end,
                        )
                        if np.isfinite(values[idx]):
                            record["primary_value"] = float(values[idx])
                        records.append(record)

            records.sort(key=lambda r: r["frame"])
            for event_index, record in enumerate(records, start=1):
                record["event_index"] = event_index

            def same_auto_batch(row: dict) -> bool:
                if not (
                    row.get("_origin") in {"auto", "manual_adjusted"}
                    and row.get("event_label") == label
                    and row.get("bodypart") == bp
                    and row.get("primary_axis") == axis
                    and not bool(row.get("_confirmed", True))
                ):
                    return False
                old_start = int(row.get("range_start", row.get("frame", -1)))
                old_end = int(row.get("range_end", row.get("frame", -1)))
                return not (old_end < start or old_start > end)

            self._push_history(f"find peaks {bp}/{axis} {start}-{end}")
            self.session_rows = [row for row in self.session_rows if not same_auto_batch(row)]
            # Replace overlapping *draft* auto batches for this same signal, and
            # never duplicate a frame that has already been confirmed.
            existing_confirmed_frames = {
                int(row.get("frame", -1)) for row in self.session_rows
                if bool(row.get("_confirmed", True))
                and row.get("event_label") == label
                and row.get("bodypart") == bp
                and row.get("primary_axis") == axis
            }
            records = [row for row in records if int(row.get("frame", -1)) not in existing_confirmed_frames]
            self.session_rows.extend(records)
            self._renumber_group(label, bp, axis)

            self._set_busy("Updating event dataset", 2)
            self._refresh_table()
            self._update_range_summary()
            self._set_busy("Refreshing plot", 3)
            self.render_plot()
            self.message.emit(
                f"Detected {len(records)} peak candidate(s) for {bp}/{axis.upper()} in frames {start}-{end}."
            )
            if not records:
                QMessageBox.information(
                    self,
                    "No peaks found",
                    "No peaks matched the current range and settings. Try a lower prominence, smaller distance, or another axis.",
                )
        except Exception as exc:
            QMessageBox.critical(self, "Peak detection failed", str(exc))
        finally:
            self._set_busy()

    def _draft_rows_for_current_range(self) -> list[dict]:
        if self.df is None:
            return []
        bp = self.bodypart.currentText()
        axis = self._primary_axis_key()
        if axis is None:
            return []
        start, end = sorted((self.range_start.value(), self.range_end.value()))
        return [
            row for row in self.session_rows
            if not bool(row.get("_confirmed", True))
            and row.get("bodypart") == bp
            and row.get("primary_axis") == axis
            and int(row.get("range_start", -1)) == start
            and int(row.get("range_end", -1)) == end
        ]

    def _update_draft_status(self):
        if not hasattr(self, "draft_status"):
            return
        drafts = self._draft_rows_for_current_range()
        confirmed = sum(1 for row in self.session_rows if bool(row.get("_confirmed", True)) and row.get("keep", True))
        if drafts:
            self.draft_status.setText(
                f"{len(drafts)} draft peak(s) in this range • {confirmed} confirmed peak(s) retained across the recording"
            )
        else:
            self.draft_status.setText(f"No draft in this range • {confirmed} confirmed peak(s) retained")

    def confirm_current_range(self):
        drafts = self._draft_rows_for_current_range()
        if not drafts:
            QMessageBox.information(
                self,
                "No draft peaks",
                "Find/review peaks in the current working range first. There are no unconfirmed peaks to lock in.",
            )
            return
        start, end = sorted((self.range_start.value(), self.range_end.value()))
        self._push_history(f"confirm range {start}-{end}")
        for row in drafts:
            row["_confirmed"] = True
        self._selected_peak_uid = None
        self.range_start.setValue(self._full_start)
        self.range_end.setValue(self._full_end)
        self.pick_range.blockSignals(True)
        self.pick_range.setChecked(False)
        self.pick_range.blockSignals(False)
        self.pick_range.setText("SELECT RANGE ON PLOT")
        self._refresh_table()
        self.render_plot()
        self.message.emit(
            f"Confirmed {len(drafts)} reviewed peak(s) from frames {start}-{end}. Returned to the full graph for the next selection."
        )

    def discard_current_draft(self):
        drafts = self._draft_rows_for_current_range()
        if not drafts:
            return
        start, end = sorted((self.range_start.value(), self.range_end.value()))
        ids = {id(row) for row in drafts}
        self._push_history(f"discard draft {start}-{end}")
        self.session_rows = [row for row in self.session_rows if id(row) not in ids]
        self._selected_peak_uid = None
        self._refresh_table()
        self.render_plot()
        self.message.emit(f"Discarded {len(drafts)} unconfirmed peak(s) from frames {start}-{end}.")

    # ----------------------------------------------------------------------
    # Manual events and click-to-reposition review
    # ----------------------------------------------------------------------
    def add_manual_peak(self):
        if self.df is None:
            QMessageBox.information(self, "Load data first", "Load a 3D CSV before adding a manual event.")
            return
        try:
            bp = self.bodypart.currentText()
            axis = self._primary_axis_key()
            if axis is None:
                QMessageBox.information(self, "Choose a primary axis", "Choose X, Y, or Z before adding a manual event.")
                return
            frame = self._nearest_frame(int(self.manual_frame.value()))
            row = self._row_for_frame(frame)
            label = self.event_label.text().strip() or f"Passive_{bp}_movement"
            record = self._record_from_row(
                row,
                bp=bp,
                axis=axis,
                label=label,
                prominence=np.nan,
                origin="manual",
                peak_kind="manual",
                range_start=int(self.range_start.value()),
                range_end=int(self.range_end.value()),
            )
            # A manually added event is an explicit user decision, so it is
            # immediately confirmed and exportable.
            record["_confirmed"] = True
            self.session_rows.append(record)
            self._renumber_group(label, bp, axis)
            self._refresh_table()
            self.render_plot()
            self.message.emit(f"Manually added frame {frame} for {bp}.")
        except Exception as exc:
            QMessageBox.critical(self, "Could not add manual event", str(exc))

    def _selected_event_row_indices(self) -> list[int]:
        """Return table-selected rows, falling back to the plot-selected peak UID.

        Peak Lab has two views of the same event selection (plot + event table).
        Manual Review buttons should therefore work even when focus has moved away
        from the table or the table panel is collapsed/hidden.
        """
        rows = sorted({index.row() for index in self.table.selectedIndexes()}) if hasattr(self, "table") else []
        rows = [row for row in rows if 0 <= row < len(self.session_rows)]
        if rows:
            return rows
        uid = str(self._selected_peak_uid or "")
        if uid:
            for row_index, record in enumerate(self.session_rows):
                if str(record.get("_uid", "")) == uid:
                    return [row_index]
        return []

    def _restore_selected_peak_table_row(self):
        """Re-select the plot-selected event after table rebuilds without changing focus."""
        if not hasattr(self, "table") or not self._selected_peak_uid:
            return
        uid = str(self._selected_peak_uid)
        row_index = next(
            (i for i, record in enumerate(self.session_rows) if str(record.get("_uid", "")) == uid),
            None,
        )
        if row_index is None:
            self._selected_peak_uid = None
            return
        self.table.blockSignals(True)
        try:
            self.table.clearSelection()
            self.table.selectRow(row_index)
        finally:
            self.table.blockSignals(False)

    def _update_selected_peak_highlight(self):
        """Enlarge the selected Plotly peak in place, preserving the current zoom."""
        if self.web is None:
            return
        uid_json = json.dumps(str(self._selected_peak_uid or ""))
        js = f"""
        (function() {{
          var plot = document.getElementById('peakPlot');
          if (!plot || !window.Plotly) return;
          var selectedUid = {uid_json};
          (plot.data || []).forEach(function(trace, traceIndex) {{
            if (!trace || trace.name !== 'Peaks' || !Array.isArray(trace.customdata)) return;
            var sizes = trace.customdata.map(function(cd) {{
              var uid = (cd && cd.length > 5) ? String(cd[5]) : '';
              var status = (cd && cd.length > 6) ? String(cd[6]) : 'Confirmed';
              if (selectedUid && uid === selectedUid) return 21;
              return status === 'Draft' ? 13 : 10;
            }});
            Plotly.restyle(plot, {{'marker.size': [sizes]}}, [traceIndex]);
          }});
        }})();
        """
        self.web.page().runJavaScript(js)

    def toggle_move_selected(self):
        """Move exactly one selected event to the Frame-box destination.

        v0.5.4 deliberately makes this independent of Plotly mouse events. This is
        the guaranteed manual-review path: select a row, type the corrected frame
        into the existing Frame spin box, and press MOVE SELECTED PEAK.
        """
        if self.df is None:
            QMessageBox.information(self, "Load data first", "Load a 3D CSV before moving an event.")
            return
        rows = self._selected_event_row_indices()
        if len(rows) != 1:
            QMessageBox.information(
                self,
                "Select one event",
                "Select one peak on the graph (or one row in EVENT DATASET), enter the corrected destination in the Frame box, then press MOVE SELECTED PEAK.",
            )
            return
        row_index = rows[0]
        if not (0 <= row_index < len(self.session_rows)):
            return
        record = self.session_rows[row_index]
        bp = str(record.get("bodypart", ""))
        axis = str(record.get("primary_axis", "z"))
        if bp in [self.bodypart.itemText(i) for i in range(self.bodypart.count())]:
            self.bodypart.setCurrentText(bp)
        if axis in {"x", "y", "z"}:
            self.primary_axis.setCurrentText(axis)

        destination = self._nearest_frame(int(self.manual_frame.value()))
        current = int(record.get("frame", destination))
        if destination == current:
            self.move_status.setText(
                f"Selected peak is already at frame {current}. Change the Frame value, then press MOVE SELECTED PEAK."
            )
            self.move_status.show()
            self.message.emit(
                f"Selected event at frame {current}. Enter a different destination in MANUAL REVIEW > Frame."
            )
            return

        self._push_history(f"move event {current} -> {destination}")
        self._selected_peak_uid = str(record.get("_uid", "")) or None
        self._move_event_to_frame(row_index, destination)

    def _move_event_to_frame(self, row_index: int, frame: int):
        if self.df is None or not (0 <= row_index < len(self.session_rows)):
            self._cancel_move_mode()
            return
        record = self.session_rows[row_index]
        bp = str(record.get("bodypart", self.bodypart.currentText()))
        axis = str(record.get("primary_axis") or self._primary_axis_key() or "z")
        row = self._row_for_frame(frame)
        record.update(self._coordinates_from_row(row, bp, axis))
        record["frame"] = int(row["frame"])
        record["time_seconds"] = self._optional_float(row, "time_seconds")
        record["timestamp"] = str(row["timestamp"]) if "timestamp" in self.df.columns else ""
        record["prominence"] = np.nan
        record["_origin"] = "manual_adjusted"
        label = str(record.get("event_label", ""))
        self._renumber_group(label, bp, axis)
        self._cancel_move_mode()
        self._refresh_table()
        self.render_plot()
        self.message.emit(f"Moved event to frame {int(row['frame'])}; time and XYZ coordinates were updated together.")

    def _cancel_move_mode(self):
        self._move_row = None
        if hasattr(self, "move_selected"):
            self.move_selected.setText("MOVE SELECTED PEAK")
        if hasattr(self, "move_status"):
            self.move_status.hide()

    # ----------------------------------------------------------------------
    # Record helpers
    # ----------------------------------------------------------------------
    def _nearest_frame(self, target: int) -> int:
        if self.df is None:
            return target
        frames = self.df["frame"].to_numpy(dtype=int)
        return int(frames[int(np.argmin(np.abs(frames - target)))])

    def _row_for_frame(self, frame: int) -> pd.Series:
        assert self.df is not None
        exact = self.df[self.df["frame"] == int(frame)]
        if not exact.empty:
            return exact.iloc[0]
        nearest = int(np.argmin(np.abs(self.df["frame"].to_numpy(dtype=int) - int(frame))))
        return self.df.iloc[nearest]

    @staticmethod
    def _optional_float(row: pd.Series, column: str) -> float:
        if column in row.index and pd.notna(row[column]):
            return float(row[column])
        return np.nan

    def _coordinates_from_row(self, row: pd.Series, bp: str, axis: str) -> dict:
        values = {}
        for coord in ("x", "y", "z"):
            value = row.get(f"{bp}_{coord}", np.nan)
            values[coord] = float(value) if pd.notna(value) else np.nan
        velocity = row.get(f"{bp}_velocity_3d", np.nan)
        values["velocity_3d"] = float(velocity) if pd.notna(velocity) else np.nan
        values["primary_axis"] = axis
        primary = row.get(f"{bp}_{axis}", np.nan)
        values["primary_value"] = float(primary) if pd.notna(primary) else np.nan
        return values

    def _record_from_row(
        self,
        row: pd.Series,
        *,
        bp: str,
        axis: str,
        label: str,
        prominence: float,
        origin: str,
        peak_kind: str,
        range_start: int,
        range_end: int,
    ) -> dict:
        record = {
            "keep": True,
            "event_label": label,
            "bodypart": bp,
            "event_index": 0,
            "frame": int(row["frame"]),
            "time_seconds": self._optional_float(row, "time_seconds"),
            "timestamp": str(row["timestamp"]) if self.df is not None and "timestamp" in self.df.columns else "",
            "prominence": prominence,
            "range_start": int(range_start),
            "range_end": int(range_end),
            "_origin": origin,
            "_peak_kind": peak_kind,
            "_confirmed": False,
            "_uid": uuid.uuid4().hex,
        }
        record.update(self._coordinates_from_row(row, bp, axis))
        return record

    def _renumber_group(self, label: str, bp: str, axis: str | None = None):
        """Number events chronologically within label + bodypart + primary axis."""
        if axis is None:
            axes = sorted({str(r.get("primary_axis", "")) for r in self.session_rows if r.get("event_label") == label and r.get("bodypart") == bp})
        else:
            axes = [axis]
        for axis_key in axes:
            matching = [
                r for r in self.session_rows
                if r.get("event_label") == label
                and r.get("bodypart") == bp
                and str(r.get("primary_axis", "")) == str(axis_key)
            ]
            matching.sort(key=lambda r: int(r.get("frame", 0)))
            for index, record in enumerate(matching, start=1):
                record["event_index"] = index

    def _sort_session_rows(self):
        axis_order = {"x": 0, "y": 1, "z": 2}
        self.session_rows.sort(
            key=lambda r: (
                str(r.get("event_label", "")),
                str(r.get("bodypart", "")),
                axis_order.get(str(r.get("primary_axis", "")).lower(), 9),
                int(r.get("frame", 0)),
                str(r.get("_uid", "")),
            )
        )

    def _renumber_all_groups(self):
        groups = {
            (str(r.get("event_label", "")), str(r.get("bodypart", "")), str(r.get("primary_axis", "")))
            for r in self.session_rows
        }
        for label, bp, axis in groups:
            self._renumber_group(label, bp, axis)
        self._sort_session_rows()

    # ----------------------------------------------------------------------
    # Table and export
    # ----------------------------------------------------------------------
    def _refresh_table(self):
        self._cancel_move_mode()
        self._renumber_all_groups()
        self._refreshing_table = True
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(self.session_rows))
            for r, record in enumerate(self.session_rows):
                for c, column in enumerate(self.TABLE_COLUMNS):
                    if column == "keep":
                        item = QTableWidgetItem("")
                        item.setCheckState(
                            Qt.CheckState.Checked if bool(record.get("keep", True)) else Qt.CheckState.Unchecked
                        )
                    else:
                        value = record.get(column, "")
                        if isinstance(value, float) and np.isnan(value):
                            value = ""
                        item = QTableWidgetItem(str(value))
                    self.table.setItem(r, c, item)
        finally:
            self.table.blockSignals(False)
            self._refreshing_table = False
        confirmed = sum(1 for row in self.session_rows if bool(row.get("_confirmed", True)))
        drafts = len(self.session_rows) - confirmed
        self.table_count.setText(f"{len(self.session_rows)} event(s) • {confirmed} confirmed • {drafts} draft")
        self._update_context_bar()
        self._update_draft_status()
        self._restore_selected_peak_table_row()
        self._update_selected_peak_highlight()

    def _table_selection_changed(self):
        """Mirror a single selected event into the existing manual Frame control."""
        if self._refreshing_table or not hasattr(self, "table"):
            return
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if len(rows) != 1 or not (0 <= rows[0] < len(self.session_rows)):
            return
        record = self.session_rows[rows[0]]
        try:
            frame = int(record.get("frame", self.manual_frame.value()))
            self.manual_frame.setValue(self._nearest_frame(frame))
        except Exception:
            pass
        self._selected_peak_uid = str(record.get("_uid", "")) or None
        # Highlight in place instead of rebuilding the Plotly page, so selecting
        # an event makes its dot visibly larger without changing the zoom window.
        self._update_selected_peak_highlight()

    def _table_item_changed(self, item: QTableWidgetItem):
        if self._refreshing_table:
            return
        if item.column() == 0 and 0 <= item.row() < len(self.session_rows):
            self.session_rows[item.row()]["keep"] = item.checkState() == Qt.CheckState.Checked
            self.render_plot()

    def _sync_keep_from_table(self):
        if not hasattr(self, "table"):
            return
        for r, record in enumerate(self.session_rows):
            item = self.table.item(r, 0)
            if item:
                record["keep"] = item.checkState() == Qt.CheckState.Checked

    def remove_selected_rows(self):
        self._cancel_move_mode()
        rows = sorted(self._selected_event_row_indices(), reverse=True)
        if not rows:
            QMessageBox.information(
                self,
                "Select a peak",
                "Select one or more event rows, or click a peak on the graph first, then press REMOVE SELECTED PEAK.",
            )
            return
        removed_uids = {
            str(self.session_rows[row].get("_uid", ""))
            for row in rows
            if 0 <= row < len(self.session_rows)
        }
        groups = set()
        for row in rows:
            if 0 <= row < len(self.session_rows):
                record = self.session_rows[row]
                groups.add((str(record.get("event_label", "")), str(record.get("bodypart", "")), str(record.get("primary_axis", ""))))
                self.session_rows.pop(row)
        for label, bp, axis in groups:
            self._renumber_group(label, bp, axis)
        if str(self._selected_peak_uid or "") in removed_uids:
            self._selected_peak_uid = None
        self._refresh_table()
        self.render_plot()

    def confirm_kept_drafts(self):
        """Confirm all checked draft events, regardless of which range is open."""
        self._sync_keep_from_table()
        drafts = [row for row in self.session_rows if row.get("keep", True) and not bool(row.get("_confirmed", True))]
        if not drafts:
            QMessageBox.information(self, "No kept drafts", "There are no checked draft events waiting for confirmation.")
            return
        self._push_history("confirm all kept drafts")
        for row in drafts:
            row["_confirmed"] = True
        self._refresh_table()
        self.render_plot()
        self.message.emit(f"Confirmed {len(drafts)} kept draft event(s). They are now exportable.")

    def clear_table(self):
        if self.session_rows:
            result = QMessageBox.question(
                self,
                "Clear event dataset?",
                "Remove every event row from the current Peak Lab session?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        self.session_rows.clear()
        self._refresh_table()
        self.render_plot()

    def export_kept_csv(self):
        self._sync_keep_from_table()
        kept = [row for row in self.session_rows if row.get("keep", True) and bool(row.get("_confirmed", True))]
        if not kept:
            drafts = sum(1 for row in self.session_rows if row.get("keep", True) and not bool(row.get("_confirmed", True)))
            message = "There are no confirmed kept event rows in the dataset."
            if drafts:
                message += f" {drafts} checked draft row(s) remain. Press ✓ CONFIRM KEPT beside the table (or CONFIRM RANGE + CONTINUE) before exporting."
            QMessageBox.information(self, "Nothing to export", message)
            return
        default = "motion_peak_events.csv"
        if self.source_path:
            default = str(self.source_path.parent / default)
        path, _ = QFileDialog.getSaveFileName(self, "Export peak events", default, "CSV files (*.csv)")
        if not path:
            return
        export_rows = [{column: row.get(column, "") for column in self.TABLE_COLUMNS} for row in kept]
        pd.DataFrame(export_rows, columns=self.TABLE_COLUMNS).to_csv(path, index=False)
        self._maybe_save_session_with_export(Path(path))
        self.message.emit(f"Exported {len(kept)} kept event rows -> {path}")

    def export_kept_mat(self):
        self._sync_keep_from_table()
        kept = [row for row in self.session_rows if row.get("keep", True) and bool(row.get("_confirmed", True))]
        if not kept:
            drafts = sum(1 for row in self.session_rows if row.get("keep", True) and not bool(row.get("_confirmed", True)))
            message = "There are no confirmed kept event rows in the dataset."
            if drafts:
                message += f" {drafts} checked draft row(s) remain. Press ✓ CONFIRM KEPT beside the table (or CONFIRM RANGE + CONTINUE) before exporting."
            QMessageBox.information(self, "Nothing to export", message)
            return
        default = "motion_peak_events.mat"
        if self.source_path:
            default = str(self.source_path.parent / default)
        path, _ = QFileDialog.getSaveFileName(self, "Export peak events for MATLAB", default, "MATLAB files (*.mat)")
        if not path:
            return
        frame = pd.DataFrame(
            [{column: row.get(column, "") for column in self.TABLE_COLUMNS} for row in kept],
            columns=self.TABLE_COLUMNS,
        )
        mat_struct = {}
        for column in frame.columns:
            series = frame[column]
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.notna().sum() == len(series):
                mat_struct[column] = numeric.to_numpy()
            else:
                mat_struct[column] = np.asarray(["" if pd.isna(v) else str(v) for v in series], dtype=object)
        savemat(path, {"peak_events": mat_struct, "source_csv": str(self.source_path or "")}, do_compression=True)
        self._maybe_save_session_with_export(Path(path))
        self.message.emit(f"Exported {len(kept)} kept event rows for MATLAB -> {path}")

    # ----------------------------------------------------------------------
    # Session persistence
    # ----------------------------------------------------------------------
    def _session_payload(self) -> dict:
        self._sync_keep_from_table()
        return {
            "session_format": "motion_pipeline_peak_lab_v0.5.7",
            "source_csv": str(self.source_path) if self.source_path else "",
            "bodypart": self.bodypart.currentText(),
            "primary_axis": self.primary_axis.currentText(),
            "direction": self.direction.currentData() or "maxima",
            "event_label": self.event_label.text(),
            "range_start": self.range_start.value(),
            "range_end": self.range_end.value(),
            "last_zoom": list(self._last_zoom) if self._last_zoom is not None else None,
            "show_x": self.show_x.isChecked(),
            "show_y": self.show_y.isChecked(),
            "show_z": self.show_z.isChecked(),
            "trace_layout": self.trace_layout_mode.currentData() or "primary_top",
            "trace_palette": self.trace_palette.currentData() or "coral_grove",
            "hover_details": self.hover_details.isChecked(),
            "overview_slider": self.overview_slider.isChecked(),
            "auto_prominence": self.auto_prominence.isChecked(),
            "prominence": self.prominence.value(),
            "distance": self.distance.value(),
            "width": self.width.value(),
            "fill_short_gaps": self.fill_short_gaps.isChecked(),
            "max_gap": self.max_gap.value(),
            "smoothing": self.smoothing.currentData() or "none",
            "savgol_window": self.savgol_window.value(),
            "savgol_poly": self.savgol_poly.value(),
            "butter_cutoff": self.butter_cutoff.value(),
            "butter_order": self.butter_order.value(),
            "show_raw_reference": self.show_raw_reference.isChecked(),
            "events": self.session_rows,
        }

    def _write_session_path(self, path: Path):
        path.write_text(json.dumps(self._session_payload(), indent=2, allow_nan=True), encoding="utf-8")
        self.message.emit(f"Saved Peak Lab review session -> {path}")

    def _maybe_save_session_with_export(self, exported_path: Path):
        if not self.save_session_with_export.isChecked():
            return
        session_path = exported_path.with_name(exported_path.stem + "_peak_session.json")
        try:
            self._write_session_path(session_path)
        except Exception as exc:
            self.message.emit(f"Could not save companion Peak Lab session: {exc}")

    def save_session(self):
        default = "peak_session.json"
        if self.source_path:
            default = str(self.source_path.parent / default)
        path, _ = QFileDialog.getSaveFileName(self, "Save peak session", default, "JSON files (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        self._write_session_path(Path(path))

    def open_session(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open peak session", "", "JSON files (*.json)")
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            source = payload.get("source_csv", "")
            if source:
                self.csv_path.setText(source)
                self.load_csv()
            available = [self.bodypart.itemText(i) for i in range(self.bodypart.count())]
            if payload.get("bodypart") in available:
                self.bodypart.setCurrentText(payload["bodypart"])
            self.primary_axis.setCurrentText(payload.get("primary_axis", "z"))
            saved_direction = str(payload.get("direction", "maxima"))
            legacy_map = {
                "Maximum (top)": "maxima",
                "Minimum (bottom)": "minima",
                "Both": "both",
            }
            saved_direction = legacy_map.get(saved_direction, saved_direction)
            direction_index = self.direction.findData(saved_direction)
            self.direction.setCurrentIndex(direction_index if direction_index >= 0 else 0)
            self.event_label.setText(payload.get("event_label", ""))
            self.range_start.setValue(int(payload.get("range_start", self.range_start.value())))
            self.range_end.setValue(int(payload.get("range_end", self.range_end.value())))
            self.show_x.setChecked(bool(payload.get("show_x", False)))
            self.show_y.setChecked(bool(payload.get("show_y", False)))
            self.show_z.setChecked(bool(payload.get("show_z", True)))
            layout_index = self.trace_layout_mode.findData(str(payload.get("trace_layout", "primary_top")))
            self.trace_layout_mode.setCurrentIndex(layout_index if layout_index >= 0 else 2)
            palette_index = self.trace_palette.findData(str(payload.get("trace_palette", "coral_grove")))
            self.trace_palette.setCurrentIndex(palette_index if palette_index >= 0 else 0)
            saved_zoom = payload.get("last_zoom")
            if isinstance(saved_zoom, (list, tuple)) and len(saved_zoom) == 2:
                try:
                    self._last_zoom = (float(saved_zoom[0]), float(saved_zoom[1]))
                except Exception:
                    self._last_zoom = None
            else:
                self._last_zoom = None
            self.hover_details.setChecked(bool(payload.get("hover_details", True)))
            self.overview_slider.setChecked(bool(payload.get("overview_slider", False)))
            self.auto_prominence.setChecked(bool(payload.get("auto_prominence", True)))
            self.prominence.setValue(float(payload.get("prominence", 5.0)))
            self.distance.setValue(int(payload.get("distance", 20)))
            self.width.setValue(float(payload.get("width", 0.0)))
            self.fill_short_gaps.setChecked(bool(payload.get("fill_short_gaps", False)))
            self.max_gap.setValue(int(payload.get("max_gap", 5)))
            smooth_index = self.smoothing.findData(str(payload.get("smoothing", "none")))
            self.smoothing.setCurrentIndex(smooth_index if smooth_index >= 0 else 0)
            self.savgol_window.setValue(int(payload.get("savgol_window", 11)))
            self.savgol_poly.setValue(int(payload.get("savgol_poly", 2)))
            self.butter_cutoff.setValue(float(payload.get("butter_cutoff", 6.0)))
            self.butter_order.setValue(int(payload.get("butter_order", 4)))
            self.show_raw_reference.setChecked(bool(payload.get("show_raw_reference", True)))

            # Backward compatible with v0.1 sessions: ignore the old source_file,
            # data_version and peak_type fields instead of exposing them again.
            cleaned = []
            for old in list(payload.get("events", [])):
                row = {column: old.get(column, "") for column in self.TABLE_COLUMNS}
                row["keep"] = bool(old.get("keep", True))
                row["_origin"] = old.get("_origin", "manual" if old.get("peak_type") == "manual" else "auto")
                old_kind = old.get("_peak_kind")
                if not old_kind:
                    legacy_peak = str(old.get("peak_type", "")).lower()
                    if legacy_peak == "manual":
                        old_kind = "manual"
                    else:
                        old_kind = {"maxima": "maximum", "minima": "minimum"}.get(saved_direction, "unknown")
                row["_peak_kind"] = old_kind
                row["_confirmed"] = bool(old.get("_confirmed", True))
                row["_uid"] = str(old.get("_uid") or uuid.uuid4().hex)
                cleaned.append(row)
            self.session_rows = cleaned
            self._refresh_table()
            self.render_plot()
            self.message.emit(f"Opened peak session -> {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Could not open session", str(exc))
