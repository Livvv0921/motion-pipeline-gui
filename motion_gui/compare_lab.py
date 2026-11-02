from __future__ import annotations

import colorsys
import json
from pathlib import Path
import re
import tempfile

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
from plotly.offline import get_plotlyjs

from PySide6.QtCore import QUrl, Signal, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
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
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None
    WEBENGINE_AVAILABLE = False

from .theme import comparison_palette, plot_palette, trace_palette_items
from .widgets import PathRow


def infer_bodyparts(columns) -> list[str]:
    axes: dict[str, set[str]] = {}
    for column in columns:
        match = re.match(r"^(.+)_([xyz])$", str(column))
        if match:
            axes.setdefault(match.group(1), set()).add(match.group(2))
    return sorted(name for name, found in axes.items() if {"x", "y", "z"}.issubset(found))


class CompareLab(QWidget):
    """Compare user-selected traces from different recordings/conditions/files."""

    message = Signal(str)

    TABLE_COLUMNS = ["label", "file", "bodypart", "axis", "start", "end"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = "dark"
        self.trace_specs: list[dict] = []
        self._loaded_source: pd.DataFrame | None = None
        self._loaded_path: Path | None = None
        self._html_path: Path | None = None
        self._plotly_js_path: Path | None = None
        self._last_fig = None
        self._recommended_export_height = 700

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        hint = QLabel(
            "Build one comparison figure from any set of 3D CSV files: load a source → choose bodypart/axis → add it → compare as an overlay or vertically stacked traces → export PNG, SVG, PDF, or interactive HTML."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        workspace = QSplitter(Qt.Orientation.Horizontal)

        # --------------------------------------------------------------
        # Left controls
        # --------------------------------------------------------------
        controls = QWidget()
        # Keep the classic left-panel layout, but allow it to contract enough
        # that the Plotly pane never paints over/clips it on narrower windows.
        controls.setMinimumWidth(270)
        controls.setMaximumWidth(500)
        controls.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(0, 0, 6, 0)
        cl.setSpacing(8)

        source_group = QGroupBox("ADD TRACE")
        sf = QFormLayout(source_group)
        sf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.csv_path = PathRow("Select any triangulated 3D CSV", mode="file", filter_text="CSV files (*.csv)")
        self.read_source = QPushButton("READ SOURCE")
        self.read_source.setObjectName("accentButton")
        self.read_source.clicked.connect(self.load_source)
        self.trace_label = QLineEdit()
        self.trace_label.setPlaceholderText("e.g. Kimchi 2026-08-17 / baseline")
        self.bodypart = QComboBox()
        self.axis = QComboBox()
        self.axis.addItems(["x", "y", "z"])
        self.axis.setCurrentText("x")
        self.start_frame = QSpinBox()
        self.start_frame.setRange(0, 2_000_000_000)
        self.end_frame = QSpinBox()
        self.end_frame.setRange(0, 2_000_000_000)
        self.add_trace = QPushButton("＋ ADD TRACE TO COMPARISON")
        self.add_trace.setObjectName("peakButton")
        self.add_trace.clicked.connect(self.add_current_trace)
        sf.addRow(self.csv_path)
        sf.addRow(self.read_source)
        sf.addRow("Trace label", self.trace_label)
        sf.addRow("Bodypart", self.bodypart)
        sf.addRow("Axis", self.axis)
        sf.addRow("Start frame", self.start_frame)
        sf.addRow("End frame", self.end_frame)
        sf.addRow(self.add_trace)
        cl.addWidget(source_group)

        plot_group = QGroupBox("COMPARISON PLOT")
        pf = QFormLayout(plot_group)
        pf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.title = QLineEdit("Tracking comparison")
        self.y_label = QLineEdit("3D coordinate value")
        self.y_label.setPlaceholderText("e.g. Left hand X position (mm)")
        self.plot_mode = QComboBox()
        self.plot_mode.addItem("Overlay", "overlay")
        self.plot_mode.addItem("Stacked subplots", "stacked")
        self.plot_mode.addItem("Compact stacked", "compact")
        self.x_mode = QComboBox()
        self.x_mode.addItem("Frame", "frame")
        self.x_mode.addItem("Elapsed time (s)", "time")
        self.x_mode.addItem("Relative frame (start = 0)", "relative")
        self.palette = QComboBox()
        for key, name in trace_palette_items():
            self.palette.addItem(name, key)
        self.line_width = QSpinBox()
        self.line_width.setRange(1, 8)
        self.line_width.setValue(2)
        self.show_legend = QCheckBox("Show trace labels / legend")
        self.show_legend.setChecked(True)
        self.show_hover = QCheckBox("Show hover details")
        self.show_hover.setChecked(True)
        self.show_grid = QCheckBox("Show grid")
        self.show_grid.setChecked(True)
        self.generate = QPushButton("UPDATE COMPARISON")
        self.generate.setObjectName("runButton")
        self.generate.clicked.connect(self.render_plot)
        self.export_format = QComboBox()
        self.export_format.addItem("PNG", "png")
        self.export_format.addItem("SVG", "svg")
        self.export_format.addItem("PDF", "pdf")
        self.export_format.addItem("Interactive HTML", "html")
        self.export_figure = QPushButton("EXPORT FULL FIGURE")
        self.export_figure.setToolTip("Export PNG/SVG/PDF with kaleido, or a self-contained interactive Plotly HTML file.")
        self.export_figure.clicked.connect(self.save_figure)
        pf.addRow("Graph title", self.title)
        pf.addRow("Plot mode", self.plot_mode)
        pf.addRow("Y-axis label", self.y_label)
        pf.addRow("X axis", self.x_mode)
        pf.addRow("Trace palette", self.palette)
        pf.addRow("Line width", self.line_width)
        pf.addRow(self.show_legend)
        pf.addRow(self.show_hover)
        pf.addRow(self.show_grid)
        pf.addRow(self.generate)
        pf.addRow("Export format", self.export_format)
        pf.addRow(self.export_figure)
        cl.addWidget(plot_group)

        note = QLabel(
            "Tip: the default trace label is taken from the recording folder (for example 20260731_111816). You can still rename it before adding the trace."
        )
        note.setObjectName("subtitle")
        note.setWordWrap(True)
        cl.addWidget(note)
        cl.addStretch(1)

        self.control_scroll = QScrollArea()
        self.control_scroll.setWidgetResizable(True)
        self.control_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.control_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.control_scroll.setMinimumWidth(270)
        self.control_scroll.setMaximumWidth(500)
        self.control_scroll.setWidget(controls)
        workspace.addWidget(self.control_scroll)
        self.workspace = workspace

        # --------------------------------------------------------------
        # Right: plot + trace table
        # --------------------------------------------------------------
        right = QSplitter(Qt.Orientation.Vertical)
        right.setMinimumWidth(360)
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        plot_panel = QWidget()
        plot_panel.setMinimumWidth(0)
        pl = QVBoxLayout(plot_panel)
        pl.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        title = QLabel("COMPARE LAB")
        title.setObjectName("plotTitle")
        self.status = QLabel("No traces added")
        self.status.setObjectName("subtitle")
        header.addWidget(title)
        header.addStretch(1)
        self.controls_toggle = QPushButton("HIDE CONTROLS")
        self.controls_toggle.setObjectName("utilityButton")
        self.controls_toggle.setToolTip("Hide/show the left trace-selection panel so the comparison plot can use the full width.")
        self.controls_toggle.clicked.connect(self._toggle_controls)
        header.addWidget(self.controls_toggle)
        header.addWidget(self.status)
        pl.addLayout(header)

        if WEBENGINE_AVAILABLE:
            self.web = QWebEngineView()
            self.web.setMinimumWidth(0)
            self.web.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
            pl.addWidget(self.web, 1)
        else:
            self.web = None
            missing = QLabel("QtWebEngine is unavailable. Install the full PySide6 package to use Compare Lab.")
            missing.setWordWrap(True)
            pl.addWidget(missing, 1)
        right.addWidget(plot_panel)

        table_panel = QWidget()
        tl = QVBoxLayout(table_panel)
        tl.setContentsMargins(0, 0, 0, 0)
        table_head = QHBoxLayout()
        table_label = QLabel("TRACE SET")
        table_label.setObjectName("sectionTitle")
        self.table_count = QLabel("0 traces")
        self.table_count.setObjectName("subtitle")
        table_head.addWidget(table_label)
        table_head.addStretch(1)
        table_head.addWidget(self.table_count)
        tl.addLayout(table_head)

        self.table = QTableWidget(0, len(self.TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(self.TABLE_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tl.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.remove = QPushButton("REMOVE SELECTED")
        self.remove.clicked.connect(self.remove_selected)
        self.clear = QPushButton("CLEAR TRACES")
        self.clear.clicked.connect(self.clear_traces)
        buttons.addWidget(self.remove)
        buttons.addWidget(self.clear)
        buttons.addStretch(1)
        tl.addLayout(buttons)
        right.addWidget(table_panel)
        right.setSizes([610, 220])

        workspace.addWidget(right)
        workspace.setChildrenCollapsible(True)
        workspace.setCollapsible(0, True)
        workspace.setCollapsible(1, False)
        workspace.setStretchFactor(0, 0)
        workspace.setStretchFactor(1, 1)
        workspace.setSizes([370, 1050])
        root.addWidget(workspace, 1)

    def _toggle_controls(self):
        visible = not self.control_scroll.isVisible()
        self.control_scroll.setVisible(visible)
        self.controls_toggle.setText("HIDE CONTROLS" if visible else "SHOW CONTROLS")
        if visible:
            self.workspace.setSizes([370, max(700, self.workspace.width() - 370)])
        else:
            self.workspace.setSizes([0, max(900, self.workspace.width())])
        if self.web is not None:
            self.web.page().runJavaScript("setTimeout(function(){ if(window.Plotly){ var p=document.getElementById('comparePlot'); if(p) Plotly.Plots.resize(p); } }, 0);")

    def set_theme(self, theme: str):
        self.theme = theme if theme in {"light", "dark"} else "dark"
        if self.trace_specs:
            self.render_plot()

    def load_source(self):
        self._loaded_source = None
        self._loaded_path = None
        path = Path(self.csv_path.text())
        if not path.is_file():
            QMessageBox.warning(self, "CSV not found", "Select an existing 3D CSV first.")
            return
        try:
            df = pd.read_csv(path)
            if "frame" not in df.columns:
                raise KeyError("The CSV must contain a frame column.")
            bodyparts = infer_bodyparts(df.columns)
            if not bodyparts:
                raise KeyError("No complete bodypart _x/_y/_z columns were found.")
            df["frame"] = pd.to_numeric(df["frame"], errors="raise").astype(int)
            self._loaded_source = df
            self._loaded_path = path
            self.bodypart.clear()
            self.bodypart.addItems(bodyparts)
            lo = int(df["frame"].min())
            hi = int(df["frame"].max())
            self.start_frame.setRange(lo, hi)
            self.end_frame.setRange(lo, hi)
            self.start_frame.setValue(lo)
            self.end_frame.setValue(hi)
            self.trace_label.setText(self._default_trace_label(path))
            self.message.emit(f"Compare Lab source loaded: {path.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Could not read source", str(exc))


    @staticmethod
    def _default_trace_label(path: Path) -> str:
        """Prefer a session timestamp from the recording folder over the repeated CSV basename."""
        # Typical layout: .../Passive_20260731_111816/3d/raw_left_hand_right_hand_3d.csv
        candidates = []
        try:
            candidates.append(path.parent.parent.name)
        except Exception:
            pass
        candidates.extend([path.parent.name, path.stem])
        for text in candidates:
            match = re.search(r"(?<!\d)(\d{8}_\d{6})(?!\d)", str(text))
            if match:
                return match.group(1)
        for text in candidates:
            if text:
                return str(text)
        return path.stem

    def add_current_trace(self):
        if self._loaded_source is None or self._loaded_path is None:
            self.load_source()
            if self._loaded_source is None or self._loaded_path is None:
                return
        bp = self.bodypart.currentText().strip()
        axis = self.axis.currentText()
        col = f"{bp}_{axis}"
        if col not in self._loaded_source.columns:
            QMessageBox.warning(self, "Column missing", f"{col} is not present in the loaded CSV.")
            return
        start, end = sorted((self.start_frame.value(), self.end_frame.value()))
        label = self.trace_label.text().strip() or f"{self._loaded_path.stem} / {bp}_{axis}"
        self.trace_specs.append(
            {
                "label": label,
                "file": str(self._loaded_path),
                "bodypart": bp,
                "axis": axis,
                "start": int(start),
                "end": int(end),
            }
        )
        self._refresh_table()
        self.render_plot()

    def _refresh_table(self):
        self.table.setRowCount(len(self.trace_specs))
        for r, spec in enumerate(self.trace_specs):
            for c, key in enumerate(self.TABLE_COLUMNS):
                value = spec.get(key, "")
                if key == "file":
                    value = Path(str(value)).name
                self.table.setItem(r, c, QTableWidgetItem(str(value)))
        self.table_count.setText(f"{len(self.trace_specs)} trace(s)")

    def remove_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.trace_specs):
                self.trace_specs.pop(r)
        self._refresh_table()
        self.render_plot()

    def clear_traces(self):
        self.trace_specs.clear()
        self._refresh_table()
        self.render_plot()

    @staticmethod
    def _sample_gradient(stops: list[str], n: int) -> list[str]:
        if n <= 0:
            return []
        if n == 1:
            return [stops[len(stops) // 2]]

        def rgb(hex_color: str) -> np.ndarray:
            h = hex_color.lstrip("#")
            return np.array([int(h[i:i+2], 16) for i in (0, 2, 4)], dtype=float)

        def hx(v: np.ndarray) -> str:
            vals = np.clip(np.round(v), 0, 255).astype(int)
            return "#" + "".join(f"{x:02X}" for x in vals)

        stop_rgb = [rgb(c) for c in stops]
        positions = np.linspace(0.0, 1.0, len(stops))
        targets = np.linspace(0.0, 1.0, n)
        out: list[str] = []
        for t in targets:
            j = int(np.searchsorted(positions, t, side="right") - 1)
            j = max(0, min(j, len(stops) - 2))
            p0, p1 = positions[j], positions[j + 1]
            frac = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            out.append(hx(stop_rgb[j] * (1.0 - frac) + stop_rgb[j + 1] * frac))
        return out

    def _colors(self, n: int) -> list[str]:
        key = str(self.palette.currentData() or "coral_grove")
        stops = comparison_palette(key, self.theme)
        return self._sample_gradient(stops, n)

    def _load_trace(self, spec: dict) -> tuple[np.ndarray, np.ndarray]:
        path = Path(spec["file"])
        df = pd.read_csv(path)
        df["frame"] = pd.to_numeric(df["frame"], errors="coerce")
        col = f"{spec['bodypart']}_{spec['axis']}"
        if col not in df.columns:
            raise KeyError(f"{col} not found in {path.name}")
        start, end = int(spec["start"]), int(spec["end"])
        sub = df[(df["frame"] >= start) & (df["frame"] <= end)].copy()
        y = pd.to_numeric(sub[col], errors="coerce").to_numpy(dtype=float)
        mode = self.x_mode.currentData()
        if mode == "time":
            if "time_seconds" not in sub.columns:
                raise KeyError(f"time_seconds not found in {path.name}")
            x = pd.to_numeric(sub["time_seconds"], errors="coerce").to_numpy(dtype=float)
        elif mode == "relative":
            x = sub["frame"].to_numpy(dtype=float) - float(start)
        else:
            x = sub["frame"].to_numpy(dtype=float)
        return x, y


    def _trace_hover(self, spec: dict):
        if not self.show_hover.isChecked():
            return {"hoverinfo": "skip"}
        return {
            "hovertemplate": (
                f"<b>{spec['label']}</b><br>"
                f"{spec['bodypart']}_{spec['axis']}<br>"
                "x: %{x}<br>value: %{y:.4f}<extra></extra>"
            )
        }

    @staticmethod
    def _normalize_for_compact(y: np.ndarray) -> np.ndarray:
        y = np.asarray(y, dtype=float)
        out = np.full_like(y, np.nan, dtype=float)
        valid = np.isfinite(y)
        if not valid.any():
            return out
        vals = y[valid]
        center = float(np.nanmedian(vals))
        lo = float(np.nanmin(vals))
        hi = float(np.nanmax(vals))
        span = hi - lo
        if not np.isfinite(span) or span <= 0:
            span = max(abs(center), 1.0)
        scaled = (vals - center) / span
        out[valid] = scaled
        return out

    def _graph_filename_stem(self) -> str:
        """Use Graph title as the default export/modebar filename."""
        title = self.title.text().strip() or "Tracking comparison"
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._-")
        return stem or "tracking_comparison"

    def render_plot(self):
        if self.web is None:
            return

        palette = plot_palette(self.theme)
        mode = self.plot_mode.currentData() or "overlay"
        loaded: list[tuple[dict, np.ndarray, np.ndarray, str]] = []
        errors = []
        colors = self._colors(len(self.trace_specs)) if self.trace_specs else []

        for spec, color in zip(self.trace_specs, colors):
            try:
                x, y = self._load_trace(spec)
                loaded.append((spec, x, y, color))
            except Exception as exc:
                errors.append(f"{spec.get('label', 'trace')}: {exc}")

        if errors:
            self.message.emit("Compare Lab skipped trace(s): " + " | ".join(errors))

        x_title = {
            "frame": "Frame",
            "time": "Elapsed time (s)",
            "relative": "Relative frame",
        }.get(self.x_mode.currentData(), "Frame")
        y_title = self.y_label.text().strip() or "3D coordinate value"
        grid = palette["grid"] if self.show_grid.isChecked() else "rgba(0,0,0,0)"

        if mode == "stacked" and loaded:
            n = len(loaded)
            fig = make_subplots(
                rows=n,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=min(0.035, 0.18 / max(n, 1)),
            )

            finite_chunks = [y[np.isfinite(y)] for _, _, y, _ in loaded if np.isfinite(y).any()]
            common_range = None
            if finite_chunks:
                all_y = np.concatenate(finite_chunks)
                lo = float(np.nanmin(all_y))
                hi = float(np.nanmax(all_y))
                if np.isfinite(lo) and np.isfinite(hi):
                    if hi == lo:
                        pad = max(abs(lo) * 0.05, 1.0)
                    else:
                        pad = (hi - lo) * 0.06
                    common_range = [lo - pad, hi + pad]

            for row, (spec, x, y, color) in enumerate(loaded, start=1):
                trace_kwargs = self._trace_hover(spec)
                fig.add_trace(
                    go.Scattergl(
                        x=x,
                        y=y,
                        mode="lines",
                        name=spec["label"],
                        connectgaps=False,
                        line=dict(color=color, width=self.line_width.value()),
                        showlegend=False,
                        **trace_kwargs,
                    ),
                    row=row,
                    col=1,
                )
                fig.update_xaxes(gridcolor=grid, zerolinecolor=grid, automargin=True, row=row, col=1)
                fig.update_yaxes(gridcolor=grid, zerolinecolor=grid, automargin=True, range=common_range, row=row, col=1)

                if self.show_legend.isChecked():
                    axis_suffix = "" if row == 1 else str(row)
                    fig.add_annotation(
                        x=1.005,
                        y=0.5,
                        xref="paper",
                        yref=f"y{axis_suffix} domain",
                        text=spec["label"],
                        showarrow=False,
                        xanchor="left",
                        yanchor="middle",
                        font=dict(color=color, family="Courier New"),
                    )

            mid_row = (n + 1) // 2
            fig.update_yaxes(title_text=y_title, row=mid_row, col=1)
            fig.update_xaxes(title_text=x_title, row=n, col=1)
            self._recommended_export_height = max(700, 240 * n)
            fig.update_layout(
                autosize=True,
                title=self.title.text().strip() or "Tracking comparison",
                paper_bgcolor=palette["paper"],
                plot_bgcolor=palette["plot"],
                font=dict(color=palette["text"], family="Courier New"),
                hovermode="x" if self.show_hover.isChecked() else False,
                showlegend=False,
                margin=dict(l=76, r=150 if self.show_legend.isChecked() else 28, t=62, b=60),
            )

        elif mode == "compact" and loaded:
            fig = go.Figure()
            n = len(loaded)
            spacing = 1.4
            band = 0.95
            tickvals = []
            ticktext = []
            for idx, (spec, x, y, color) in enumerate(loaded):
                base = (n - 1 - idx) * spacing
                yn = self._normalize_for_compact(y)
                yplot = yn * band + base
                trace_kwargs = self._trace_hover(spec)
                fig.add_trace(
                    go.Scattergl(
                        x=x,
                        y=yplot,
                        mode="lines",
                        name=spec["label"],
                        connectgaps=False,
                        line=dict(color=color, width=self.line_width.value()),
                        showlegend=False,
                        **trace_kwargs,
                    )
                )
                tickvals.append(base)
                ticktext.append(spec["label"] if self.show_legend.isChecked() else "")
                if self.show_legend.isChecked():
                    fig.add_annotation(
                        x=1.005, y=base, xref="paper", yref="y", text=spec["label"],
                        showarrow=False, xanchor="left", yanchor="middle",
                        font=dict(color=color, family="Courier New")
                    )
            self._recommended_export_height = max(700, 125 * n + 240)
            fig.update_layout(
                autosize=True,
                title=self.title.text().strip() or "Tracking comparison",
                paper_bgcolor=palette["paper"],
                plot_bgcolor=palette["plot"],
                font=dict(color=palette["text"], family="Courier New"),
                xaxis_title=x_title,
                yaxis_title=y_title,
                hovermode="x" if self.show_hover.isChecked() else False,
                showlegend=False,
                margin=dict(l=85, r=165 if self.show_legend.isChecked() else 28, t=62, b=60),
            )
            fig.update_xaxes(gridcolor=grid, zerolinecolor=grid, automargin=True)
            fig.update_yaxes(
                gridcolor="rgba(0,0,0,0)",
                zerolinecolor="rgba(0,0,0,0)",
                tickmode="array",
                tickvals=tickvals if self.show_legend.isChecked() else [],
                ticktext=ticktext if self.show_legend.isChecked() else [],
                showticklabels=False,
                automargin=True,
            )

        else:
            self._recommended_export_height = 700
            fig = go.Figure()
            for spec, x, y, color in loaded:
                trace_kwargs = self._trace_hover(spec)
                fig.add_trace(
                    go.Scattergl(
                        x=x,
                        y=y,
                        mode="lines",
                        name=spec["label"],
                        connectgaps=False,
                        line=dict(color=color, width=self.line_width.value()),
                        **trace_kwargs,
                    )
                )
            fig.update_layout(
                autosize=True,
                title=self.title.text().strip() or "Tracking comparison",
                paper_bgcolor=palette["paper"],
                plot_bgcolor=palette["plot"],
                font=dict(color=palette["text"], family="Courier New"),
                xaxis_title=x_title,
                yaxis_title=y_title,
                hovermode="x unified" if self.show_hover.isChecked() else False,
                showlegend=self.show_legend.isChecked(),
                margin=dict(l=65, r=24, t=62, b=60),
                legend=dict(bgcolor="rgba(0,0,0,0)"),
            )
            fig.update_xaxes(gridcolor=grid, zerolinecolor=grid, automargin=True)
            fig.update_yaxes(gridcolor=grid, zerolinecolor=grid, automargin=True)

        self._last_fig = fig
        config = {"displaylogo": False, "scrollZoom": True, "responsive": True, "toImageButtonOptions": {"format": "png", "filename": self._graph_filename_stem(), "scale": 2}}

        if self._plotly_js_path is None:
            cache_dir = Path(tempfile.gettempdir()) / "motion_pipeline_gui"
            cache_dir.mkdir(parents=True, exist_ok=True)
            js_path = cache_dir / "plotly.min.js"
            if not js_path.is_file():
                js_path.write_text(get_plotlyjs(), encoding="utf-8")
            self._plotly_js_path = js_path

        html = fig.to_html(include_plotlyjs=False, full_html=True, div_id="comparePlot", config=config)
        fill_css = "<style>html,body,#comparePlot{width:100%;height:100%;margin:0;padding:0;overflow:hidden;} body>div{height:100% !important;}</style>"
        resize_js = "<script>window.addEventListener('resize',function(){var p=document.getElementById('comparePlot');if(p&&window.Plotly){Plotly.Plots.resize(p);}});</script>"
        html = html.replace("</head>", f'<script src="{self._plotly_js_path.resolve().as_uri()}"></script>{fill_css}{resize_js}</head>')
        if self._html_path:
            try:
                self._html_path.unlink(missing_ok=True)
            except Exception:
                pass
        fd = tempfile.NamedTemporaryFile(mode="w", suffix=".html", prefix="motion_compare_", delete=False, encoding="utf-8")
        with fd:
            fd.write(html)
        self._html_path = Path(fd.name)
        self.web.load(QUrl.fromLocalFile(str(self._html_path)))
        mode_label = {"stacked": "stacked subplots", "compact": "compact stacked", "overlay": "overlay"}.get(mode, mode)
        self.status.setText(f"{len(self.trace_specs)} trace(s) • {mode_label} • {x_title}")

    def save_figure(self):
        if self._last_fig is None or not self.trace_specs:
            QMessageBox.information(self, "Nothing to export", "Add and render at least one trace first.")
            return
        fmt = str(self.export_format.currentData() or "png")
        ext = fmt
        default = f"{self._graph_filename_stem()}.{ext}"
        if self._loaded_path:
            default = str(self._loaded_path.parent / default)
        filters = {
            "png": "PNG image (*.png)",
            "svg": "SVG vector image (*.svg)",
            "pdf": "PDF document (*.pdf)",
            "html": "Interactive HTML (*.html)",
        }
        path, _ = QFileDialog.getSaveFileName(self, f"Export comparison {fmt.upper()}", default, filters[fmt])
        if not path:
            return
        if not path.lower().endswith(f".{ext}"):
            path += f".{ext}"
        try:
            if fmt == "html":
                pio.write_html(self._last_fig, path, include_plotlyjs=True, full_html=True, auto_open=False)
            else:
                kwargs = {"format": fmt}
                if fmt == "png":
                    kwargs.update(scale=2, width=1600, height=int(self._recommended_export_height))
                pio.write_image(self._last_fig, path, **kwargs)
        except Exception as exc:
            extra = ""
            if fmt != "html":
                extra = "\n\nStatic PNG/SVG/PDF export requires kaleido in the GUI environment (pip install kaleido)."
            QMessageBox.critical(self, "Figure export failed", f"Could not export {fmt.upper()}: {exc}{extra}")
            return
        self.message.emit(f"Compare Lab full figure {fmt.upper()} exported -> {path}")

    def save_png(self):
        """Backward-compatible wrapper used by older sessions/tests."""
        index = self.export_format.findData("png")
        if index >= 0:
            self.export_format.setCurrentIndex(index)
        self.save_figure()
