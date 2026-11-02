from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .help_dialog import HelpDialog
from .pages import PassivePage, CalibrationPage, TriangulationPage, VisualizationPage
from .process_runner import ProcessRunner
from .theme import stylesheet
from .widgets import StepNavItem


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Motion Pipeline GUI — DLC / Aniposelib / Peak Lab / Movement Lab / Compare Lab")
        self.resize(1480, 900)
        self.setMinimumSize(1180, 760)
        self.settings = QSettings("MotionPipelineGUI", "MotionPipelineGUI")
        self.project_root = Path(__file__).resolve().parents[1]
        self.backend_dir = self.project_root / "backend" / "scripts"
        self.runner_script = self.project_root / "backend" / "step_runner.py"
        self.last_output_basename = ""
        self.theme = str(self.settings.value("ui/theme", "dark") or "dark").lower()
        if self.theme not in {"dark", "light"}:
            self.theme = "dark"

        self.runner = ProcessRunner(self)
        self.runner.output.connect(self.append_console)
        self.runner.step_progress.connect(self._on_step_progress)
        self.runner.overall_progress.connect(self._on_overall_progress)
        self.runner.started.connect(self._on_started)
        self.runner.finished.connect(self._on_finished)
        self.runner.active_changed.connect(self._on_active_changed)
        self._job_settings: dict[str, dict] = {}
        self._step_batch_failed: dict[str, bool] = {}

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ------------------------------------------------------------------
        # Always-visible utility bar. This keeps navigation/help/theme access
        # available even when the sidebar is hidden for a full-width Peak Lab.
        # ------------------------------------------------------------------
        utility = QFrame()
        utility.setObjectName("utilityBar")
        utility_layout = QHBoxLayout(utility)
        utility_layout.setContentsMargins(8, 5, 8, 5)
        utility_layout.setSpacing(4)

        self.sidebar_toggle = QPushButton("☰  SIDEBAR")
        self.sidebar_toggle.setObjectName("utilityButton")
        self.sidebar_toggle.setToolTip("Show/hide the Motion//Pipeline sidebar (Ctrl+B).")
        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        utility_layout.addWidget(self.sidebar_toggle)

        self.context_label = QLabel("01 / PASSIVE READING")
        self.context_label.setObjectName("subtitle")
        utility_layout.addWidget(self.context_label)
        utility_layout.addStretch(1)

        self.new_draft_button = QPushButton("＋  NEW DRAFT")
        self.new_draft_button.setObjectName("utilityButton")
        self.new_draft_button.setToolTip("Clear remembered input history and rebuild the workflow with clean defaults. Theme and layout are preserved.")
        self.new_draft_button.clicked.connect(self.new_draft)
        utility_layout.addWidget(self.new_draft_button)

        self.top_console_toggle = QPushButton("CONSOLE")
        self.top_console_toggle.setObjectName("utilityButton")
        self.top_console_toggle.setToolTip("Show/hide backend output and progress.")
        self.top_console_toggle.clicked.connect(self.toggle_console)
        utility_layout.addWidget(self.top_console_toggle)

        self.help_button = QPushButton("?  QUICK HELP")
        self.help_button.setObjectName("utilityButton")
        self.help_button.setToolTip("Open searchable help for the current page (Ctrl+H).")
        self.help_button.clicked.connect(self.open_help)
        utility_layout.addWidget(self.help_button)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("utilityButton")
        self.theme_button.clicked.connect(self.toggle_theme)
        utility_layout.addWidget(self.theme_button)
        outer.addWidget(utility)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(245)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(8, 12, 8, 12)
        side.setSpacing(5)
        brand = QLabel("MOTION//PIPELINE")
        brand.setObjectName("brandLabel")
        side.addWidget(brand)

        self.nav_items = []
        titles = ["Passive Reading", "Calibration", "Triangulation", "Visualization"]
        for i, title in enumerate(titles, 1):
            item = StepNavItem(i, title)
            item.clicked.connect(lambda idx=i - 1: self.switch_page(idx))
            self.nav_items.append(item)
            side.addWidget(item)
        side.addStretch(1)

        self.console_toggle = QPushButton("CONSOLE  ▴")
        self.console_toggle.clicked.connect(self.toggle_console)
        self.console_toggle.setToolTip("Show/hide the dockable backend console. Drag its title bar to the left, right, or bottom.")
        side.addWidget(self.console_toggle)

        stop = QPushButton("STOP ALL RUNNING")
        stop.setObjectName("dangerButton")
        stop.setToolTip("Stop every backend task currently running in this GUI.")
        stop.clicked.connect(self.runner.stop)
        side.addWidget(stop)
        body_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        # Let the central page yield vertical room to the docked console. This
        # keeps the console draggable up to roughly half of the main window.
        self.stack.setMinimumHeight(180)
        # Let QMainWindow's dock layout resize the central pages normally. Using
        # Ignored here allowed a tall page to visually fight the bottom console.
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.pages = [PassivePage(self), CalibrationPage(self), TriangulationPage(self), VisualizationPage(self)]
        for page in self.pages:
            self.stack.addWidget(page)
        body_layout.addWidget(self.stack, 1)
        outer.addWidget(body, 1)

        # ------------------------------------------------------------------
        # Dockable backend console. It can live at the bottom, left or right,
        # or be floated into a separate window by dragging its title bar.
        # ------------------------------------------------------------------
        self.console_frame = QFrame()
        self.console_frame.setObjectName("consoleFrame")
        c = QVBoxLayout(self.console_frame)
        c.setContentsMargins(8, 6, 8, 8)
        c.setSpacing(5)
        status_row = QHBoxLayout()
        self.console_status = QLabel("IDLE")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        dock_right = QPushButton("DOCK RIGHT")
        dock_right.setObjectName("utilityButton")
        dock_right.setToolTip("Dock the backend console on the right side of the GUI.")
        dock_right.clicked.connect(lambda: self._dock_console(Qt.DockWidgetArea.RightDockWidgetArea))
        dock_bottom = QPushButton("DOCK BOTTOM")
        dock_bottom.setObjectName("utilityButton")
        dock_bottom.setToolTip("Dock the backend console along the bottom of the GUI.")
        dock_bottom.clicked.connect(lambda: self._dock_console(Qt.DockWidgetArea.BottomDockWidgetArea))
        stop_console = QPushButton("STOP ALL")
        stop_console.setObjectName("dangerButton")
        stop_console.clicked.connect(self.runner.stop)
        status_row.addWidget(self.console_status)
        status_row.addWidget(self.progress, 1)
        status_row.addWidget(dock_right)
        status_row.addWidget(dock_bottom)
        status_row.addWidget(stop_console)
        c.addLayout(status_row)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(10000)
        c.addWidget(self.console, 1)

        self.setCentralWidget(central)
        self.setDockNestingEnabled(True)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.console_dock = QDockWidget("BACKEND CONSOLE — drag to left / right / bottom", self)
        self.console_dock.setObjectName("backendConsoleDock")
        self.console_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.console_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.console_dock.setWidget(self.console_frame)
        self.console_dock.setMinimumHeight(120)
        self.console_dock.setMaximumHeight(max(240, int(self.height() * 0.42)))
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.console_dock)
        self.console_dock.visibilityChanged.connect(self._console_visibility_changed)
        self.console_dock.dockLocationChanged.connect(lambda _area: self._update_console_dock_limits())
        self.console_dock.hide()

        self.help_dialog = HelpDialog(self)

        QShortcut(QKeySequence("Ctrl+B"), self, activated=self.toggle_sidebar)
        QShortcut(QKeySequence("Ctrl+H"), self, activated=self.open_help)

        sidebar_visible = self._setting_bool("ui/sidebar_visible", True)
        self.sidebar.setVisible(sidebar_visible)
        self._update_sidebar_button()
        self.apply_theme(self.theme)
        self.switch_page(0)

    def _setting_bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def switch_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, item in enumerate(self.nav_items):
            item.set_selected(i == index)
        labels = ["01 / PASSIVE READING", "02 / CALIBRATION", "03 / TRIANGULATION", "04 / VISUALIZATION"]
        if 0 <= index < len(labels):
            self.context_label.setText(labels[index])

    def toggle_sidebar(self):
        visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(visible)
        self.settings.setValue("ui/sidebar_visible", visible)
        self._update_sidebar_button()

    def _update_sidebar_button(self):
        self.sidebar_toggle.setText("☰  HIDE SIDEBAR" if self.sidebar.isVisible() else "☰  SHOW SIDEBAR")

    def _dock_console(self, area: Qt.DockWidgetArea):
        self.console_dock.setFloating(False)
        self.addDockWidget(area, self.console_dock)
        self.console_dock.show()
        self.console_dock.raise_()
        self._update_console_dock_limits()

    def toggle_console(self):
        self.console_dock.setVisible(not self.console_dock.isVisible())

    def _console_visibility_changed(self, visible: bool):
        self.console_toggle.setText("CONSOLE  ▾" if visible else "CONSOLE  ▴")
        self.top_console_toggle.setText("HIDE CONSOLE" if visible else "CONSOLE")
        if visible and not self.console_dock.isFloating() and self.dockWidgetArea(self.console_dock) == Qt.DockWidgetArea.BottomDockWidgetArea:
            target = min(max(220, self.height() // 3), max(220, int(self.height() * 0.42)))
            self.resizeDocks([self.console_dock], [target], Qt.Orientation.Vertical)

    def _update_console_dock_limits(self):
        if not hasattr(self, "console_dock"):
            return
        area = self.dockWidgetArea(self.console_dock)
        if not self.console_dock.isFloating() and area == Qt.DockWidgetArea.BottomDockWidgetArea:
            self.console_dock.setMaximumHeight(max(240, int(self.height() * 0.42)))
        else:
            self.console_dock.setMaximumHeight(16_777_215)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_console_dock_limits()

    def open_help(self):
        index = self.stack.currentIndex()
        section = {0: "Passive", 1: "Calibration", 2: "Triangulation", 3: "Visualization"}.get(index, "Overview")
        if index == 3:
            viz = self.pages[3]
            if getattr(viz, "tabs", None) is not None:
                if viz.tabs.currentIndex() == 1:
                    section = "Peak Lab"
                elif viz.tabs.currentIndex() == 2:
                    section = "Movement Lab"
                elif viz.tabs.currentIndex() == 3:
                    section = "Compare Lab"
        self.help_dialog.show_section(section)

    def new_draft(self):
        if self.runner.is_running:
            QMessageBox.warning(self, "Pipeline busy", "Stop or finish all running backend tasks before starting a new draft.")
            return
        result = QMessageBox.question(
            self,
            "Start a new draft?",
            "Clear remembered trial/model/file inputs and rebuild the workflow with clean defaults?\n\n"
            "Your GUI theme, sidebar preference, backend Python interpreters, camera count, and remembered Movement Lab protocol will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        preserve = {}
        for key in self.settings.allKeys():
            if (
                key.startswith("ui/")
                or key.startswith("env/")
                or key == "camera/count"
                or key in {"movement/default_sequence", "movement/protocol_name"}
            ):
                preserve[key] = self.settings.value(key)
        self.settings.clear()
        for key, value in preserve.items():
            self.settings.setValue(key, value)

        while self.stack.count():
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            widget.deleteLater()
        self.pages = [PassivePage(self), CalibrationPage(self), TriangulationPage(self), VisualizationPage(self)]
        for page in self.pages:
            self.stack.addWidget(page)
        self.last_output_basename = ""
        for item in self.nav_items:
            item.set_status("idle")
        self.switch_page(0)
        self.apply_theme(self.theme)
        self.append_console("[GUI] Started a new draft. Trial/model/file history was cleared; environment and lab defaults were preserved.\n")

    def toggle_theme(self):
        self.apply_theme("light" if self.theme == "dark" else "dark")

    def apply_theme(self, theme: str):
        self.theme = theme if theme in {"dark", "light"} else "dark"
        self.settings.setValue("ui/theme", self.theme)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet(self.theme))
        self.theme_button.setText("☀  LIGHT" if self.theme == "dark" else "☾  DARK")
        self.theme_button.setToolTip("Switch to light mode." if self.theme == "dark" else "Switch to dark mode.")
        # Peak Lab renders Plotly HTML, so it needs an explicit theme refresh.
        for page in getattr(self, "pages", []):
            peak_lab = getattr(page, "peak_lab", None)
            if peak_lab is not None:
                peak_lab.set_theme(self.theme)
            movement_lab = getattr(page, "movement_lab", None)
            if movement_lab is not None:
                movement_lab.set_theme(self.theme)
            compare_lab = getattr(page, "compare_lab", None)
            if compare_lab is not None:
                compare_lab.set_theme(self.theme)

    def append_console(self, text: str):
        if not text:
            return
        self.console.moveCursor(QTextCursor.End)
        self.console.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.console.ensureCursorVisible()

    def run_backend(self, step: str, python_executable: str, script_name: str, settings: dict):
        backend = self.backend_dir / script_name
        if not backend.is_file():
            QMessageBox.critical(self, "Backend missing", str(backend))
            return
        self.console_dock.show()
        self.console_dock.raise_()
        if self.runner.active_count:
            self.append_console(
                "[GUI] Parallel launch: this task will run beside existing jobs. "
                "CPU/GPU/RAM are shared, so use independent input/output folders for jobs that write files.\n"
            )
        try:
            job_id = self.runner.run(step, python_executable, self.runner_script, backend, settings)
            self._job_settings[job_id] = dict(settings)
        except Exception as exc:
            QMessageBox.critical(self, "Could not start process", str(exc))

    def _step_index(self, step: str) -> int:
        return {"passive": 0, "calibration": 1, "triangulation": 2, "visualization": 3}.get(step, -1)

    def _on_started(self, step: str, job_id: str):
        idx = self._step_index(step)
        # Reset the batch failure flag when the first job of a new stage batch starts.
        if len(self.runner.active_jobs_for_step(step)) == 1:
            self._step_batch_failed[step] = False
        if idx >= 0:
            self.nav_items[idx].set_status("running")
            self.nav_items[idx].set_progress(-1)

    def _on_step_progress(self, step: str, value: int):
        idx = self._step_index(step)
        if idx >= 0 and self.nav_items[idx].status == "running":
            self.nav_items[idx].set_progress(value)

    def _on_overall_progress(self, value: int, active_count: int):
        if active_count <= 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.console_status.setText("IDLE")
            return
        self.console_status.setText(f"RUNNING: {active_count} TASK{'S' if active_count != 1 else ''}")
        if value < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(value)

    def _on_active_changed(self, count: int):
        self.top_console_toggle.setToolTip(
            f"Show/hide backend output and progress. {count} task{'s' if count != 1 else ''} currently running."
        )

    def _on_finished(self, step: str, job_id: str, success: bool, exit_code: int):
        settings = self._job_settings.pop(job_id, {})
        self._step_batch_failed[step] = self._step_batch_failed.get(step, False) or not success
        idx = self._step_index(step)
        remaining = self.runner.active_jobs_for_step(step)
        if idx >= 0:
            if remaining:
                self.nav_items[idx].set_status("running")
            else:
                self.nav_items[idx].set_status("failed" if self._step_batch_failed.get(step, False) else "success")
        label = self.runner.job_label(job_id)
        self.append_console(
            f"[GUI] {step.upper()} {'completed successfully' if success else 'failed'} "
            f"(exit code {exit_code}; {job_id}).\n"
        )
        if success:
            self._propagate_step_outputs(step, settings)
        elif not self.runner.active_count:
            QMessageBox.warning(
                self,
                f"{step.title()} failed",
                "A backend task returned an error. Open the console to read its tagged traceback and validation messages.",
            )

    def _propagate_step_outputs(self, step: str, settings: dict):
        # Parallel jobs use the settings snapshot captured at launch. To avoid a
        # completed background job overwriting a different draft the user is
        # currently editing, downstream fields are filled only when blank.
        def set_path_if_blank(widget, value):
            if value and not widget.text().strip():
                widget.setText(str(value))

        if step == "passive":
            folders = list(settings.get("FOLDERS_TO_ANALYZE") or [])
            if len(folders) == 1:
                trial = Path(str(settings.get("PROCESS_ROOT", ""))) / folders[0]
                raw_trial = Path(str(settings.get("VIDEO_ROOT", ""))) / folders[0]
                tri = self.pages[2]
                viz = self.pages[3]
                set_path_if_blank(tri.trial, trial)
                set_path_if_blank(tri.raw_folder, raw_trial)
                set_path_if_blank(viz.trial, trial)
                set_path_if_blank(viz.movement_lab.raw_folder, raw_trial)
            if settings.get("VIDEO_ROOT") and not self.pages[2].raw_root.text().strip():
                self.pages[2].raw_root.setText(str(settings["VIDEO_ROOT"]))
        elif step == "calibration":
            folder = Path(str(settings.get("CALIBRATION_VIDEO_FOLDER", "")))
            root = Path(str(settings.get("CALIBRATION_OUTPUT_ROOT", "")))
            if folder.name:
                set_path_if_blank(self.pages[2].calibration, root / folder.name / "calibration.toml")
        elif step == "triangulation":
            viz = self.pages[3]
            trial_text = str(settings.get("TRIAL_FOLDER", ""))
            set_path_if_blank(viz.trial, trial_text)
            base = str(settings.get("OUTPUT_BASENAME", ""))
            if base and not viz.basename.text().strip():
                viz.basename.setText(base)
            parts = settings.get("BODY_PARTS") or []
            if parts and not viz.bodyparts.text().strip():
                viz.bodyparts.setText(", ".join(map(str, parts)))
            versions = list(settings.get("DATA_VERSIONS") or [])
            if trial_text and base and versions:
                csv = Path(trial_text) / "3d" / f"{versions[0]}_{base}.csv"
                set_path_if_blank(viz.peak_lab.csv_path, csv)
                set_path_if_blank(viz.movement_lab.csv_path, csv)
            set_path_if_blank(viz.movement_lab.raw_folder, settings.get("RAW_VIDEO_FOLDER") or "")



def re_split(text: str):
    import re

    return re.split(r"[,;\n]+", text)
