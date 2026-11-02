from __future__ import annotations

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


HELP_STYLE = """
<style>
body { line-height: 1.35; }
h2 { margin-bottom: 8px; }
h3 { margin-top: 15px; margin-bottom: 6px; }
ul { margin-top: 4px; margin-left: 18px; }
li { margin-bottom: 7px; }
.action { font-weight: bold; text-decoration: underline; }
.note { font-style: italic; }
</style>
"""


HELP_PAGES = {
    "Overview": HELP_STYLE + """
<h2>Motion Pipeline — Quick Help</h2>
<p>You can run <b>only the stage you need</b>. The sidebar is navigation; it does not mean Steps 1–3 must be rerun before Step 4. v0.5.7 can also run multiple independent backend jobs at the same time.</p>
<h3>Global controls</h3>
<ul>
  <li><b>SIDEBAR:</b> hide/show the four-step navigation so the active workspace can use more screen space. Shortcut: <b>Ctrl+B</b>.</li>
  <li><b>CONSOLE:</b> open the backend log and overall progress panel. Drag its title bar to the <b>left, right, or bottom</b>, float it, or use the DOCK RIGHT / DOCK BOTTOM shortcuts inside the console.</li>
  <li><b>Parallel jobs:</b> you may launch another stage while one is already running. Console lines are tagged by job and each running sidebar stage temporarily shows its own progress bar. CPU/GPU/RAM are shared, so avoid two jobs writing to the same output files.</li>
  <li><b>NEW DRAFT:</b> clear remembered trial/model/file inputs and rebuild a clean workflow. Theme, backend interpreters, camera count, and your remembered Movement Lab protocol are preserved.</li>
  <li><b>QUICK HELP:</b> open this searchable help window. Shortcut: <b>Ctrl+H</b>.</li>
  <li><b>LIGHT / DARK:</b> switch the application theme. Your choice is remembered.</li>
</ul>
<h3>Status dots</h3>
<ul>
  <li><b>Gray:</b> not run in this session.</li>
  <li><b>Pink:</b> currently running; a thin progress bar appears under that sidebar stage only while work is active.</li>
  <li><b>Green:</b> completed successfully.</li>
  <li><b>Red:</b> failed; open the Console for the traceback.</li>
</ul>
""",
    "Passive": HELP_STYLE + """
<h2>01 / Passive Reading</h2>
<p>Use an existing trained DeepLabCut model to analyze selected passive-recording folders.</p>
<h3>Inputs</h3>
<ul>
  <li><b>DLC Python:</b> the Python executable from the environment where DeepLabCut works (<code>python.exe</code> on Windows or <code>.../bin/python</code> on macOS).</li>
  <li><b>Model config:</b> the trained DeepLabCut project's <code>config.yaml</code>.</li>
  <li><b>Raw video root:</b> parent folder containing the recording folders and original videos.</li>
  <li><b>Processed root:</b> destination where DLC H5 outputs will be written.</li>
  <li><b>Recording folders:</b> one or more exact folder names to analyze.</li>
  <li><b>Video extension:</b> file type to search for, such as <code>.mp4</code>.</li>
</ul>
<h3>Existing data & filters</h3>
<ul>
  <li><b>Reanalyze existing:</b> rerun DLC even when a raw H5 result already exists.</li>
  <li><b>Apply filters:</b> enable optional post-processing of the DLC predictions.</li>
  <li><b>Filters:</b> choose Median, ARIMA, Savitzky–Golay, and/or Butterworth low-pass. All filters are OFF by default.</li>
  <li><b>Savitzky–Golay / Butterworth:</b> these optional filters are applied to DLC 2D x/y coordinates and saved as separate H5 variants so they can be triangulated into separate 3D CSV files for Compare Lab.</li>
  <li><b>Overwrite filtered outputs:</b> recreate selected filtered files instead of reusing them.</li>
</ul>
<h3>Run</h3>
<ul>
  <li><span class="action">RUN PASSIVE ANALYSIS:</span> validate the inputs and launch the existing DeepLabCut backend script.</li>
</ul>
""",
    "Calibration": HELP_STYLE + """
<h2>02 / Calibration</h2>
<p>Create an Aniposelib camera calibration from the ChArUco-board calibration videos.</p>
<h3>Files & cameras</h3>
<ul>
  <li><b>Calibration video folder:</b> folder containing one intended calibration video per physical camera.</li>
  <li><b>Processed output root:</b> parent folder where <code>calibration.toml</code> and the calibration log will be saved.</li>
  <li><b>Camera count:</b> number of physical cameras. This is manual here because the calibration TOML does not exist yet.</li>
  <li><b>Camera identifiers:</b> filename fragments used to match each physical camera in the correct order.</li>
</ul>
<h3>ChArUco board</h3>
<ul>
  <li><b>Columns / rows:</b> number of ChArUco squares on the physical board.</li>
  <li><b>Square length:</b> physical square size.</li>
  <li><b>Marker length:</b> physical ArUco marker size.</li>
  <li><b>Marker bits / dictionary size:</b> must match the printed board definition.</li>
  <li><b>FISHEYE:</b> use the fisheye camera model.</li>
  <li><b>RECALIBRATE:</b> allow an existing <code>calibration.toml</code> to be replaced.</li>
</ul>
<h3>Run</h3>
<ul>
  <li><span class="action">RUN CALIBRATION:</span> validate camera files and board settings, then perform calibration.</li>
</ul>
""",
    "Triangulation": HELP_STYLE + """
<h2>03 / Triangulation</h2>
<p>Convert multi-camera 2D DeepLabCut predictions into 3D X/Y/Z coordinates.</p>
<h3>Core inputs</h3>
<ul>
  <li><b>Anipose Python:</b> select the Python executable inside the environment where <code>aniposelib</code> works. On Windows this is commonly <code>.../envs/aniposelib/python.exe</code>; on macOS it is commonly <code>.../envs/aniposelib/bin/python</code>. Confirm it with <code>python -c "import sys; print(sys.executable)"</code> after activating the environment.</li>
  <li><b>Trial folder:</b> processed recording folder containing the camera H5 files. <b>Do not select the 3d subfolder</b>; 3D outputs are written there automatically.</li>
  <li><b>Calibration TOML:</b> <code>calibration.toml</code> created in Calibration.</li>
  <li><b>Raw video folder:</b> choose the <b>exact recording folder</b> containing Cam-0/Cam-1/... source videos. This is the preferred source for FPS/timestamps.</li>
  <li><b>Advanced raw root:</b> optional parent root used only as a fallback when the backend needs to match the trial folder automatically.</li>
  <li><b>Data versions:</b> choose <b>raw</b>, <b>median</b>, <b>ARIMA</b>, <b>savgol</b>, <b>butterworth</b>, or more than one. Raw is the only version selected by default.</li>
  <li><b>Bodyparts:</b> structures to triangulate. <b>DETECT BODYPARTS</b> reads available names from a DLC H5.</li>
</ul>
<h3>Triangulation settings</h3>
<ul>
  <li><b>Auto camera count:</b> read the camera number from <code>calibration.toml</code>; manual count remains a fallback.</li>
  <li><b>Score threshold:</b> DLC likelihood values below this threshold are treated as missing before triangulation. The spinner changes in 0.1 steps, while manual decimal entry is still allowed.</li>
  <li><b>Chunk size:</b> number of frames processed at a time.</li>
  <li><b>Overwrite existing 3D:</b> allow an existing 3D output to be replaced.</li>
  <li><b>Save checkpoints:</b> keep intermediate results after chunks for safer long runs.</li>
</ul>
<h3>Run</h3>
<ul>
  <li><span class="action">RUN TRIANGULATION:</span> create CSV/NPY 3D products containing frame, elapsed-time, timestamp, and XYZ columns.</li>
</ul>
""",
    "Visualization": HELP_STYLE + """
<h2>04 / Visualization</h2>
<p>The Visualization page contains <b>PLOTS</b>, <b>PEAK LAB</b>, <b>MOVEMENT LAB</b>, <b>COMPARE LAB</b>, and <b>HTML VIEWER</b>.</p>
<h3>PLOTS</h3>
<ul>
  <li><b>Versions:</b> choose which <b>raw / median / ARIMA / savgol / butterworth</b> 3D CSV files to visualize.</li>
  <li><b>Static PNG:</b> save Matplotlib images for QC or reports.</li>
  <li><b>Interactive Plotly HTML:</b> save zoomable/hoverable Plotly figures.</li>
  <li><b>Axis comparisons:</b> compare the same X, Y, or Z coordinate across bodyparts.</li>
  <li><b>Single traces:</b> create one coordinate trace per graph.</li>
  <li><b>XYZ combined:</b> place X/Y/Z for one bodypart on the same interactive plot.</li>
  <li><b>3D trajectories:</b> create the spatial XYZ trajectory for each bodypart.</li>
  <li><span class="action">GENERATE VISUALIZATIONS:</span> launch the visualization backend with the selected options.</li>
</ul>
<h3>HTML VIEWER</h3>
<ul>
  <li><b>Open HTML:</b> view an already-saved Plotly HTML file inside the GUI without regenerating it.</li>
  <li><b>Plotly toolbar:</b> zoom, pan, reset axes, and rotate 3D plots where supported.</li>
</ul>
<h3>PEAK LAB</h3>
<ul>
  <li><b>Purpose:</b> review one movement trace, detect candidate peaks, correct them manually, and export event timestamps/coordinates.</li>
  <li><b>Tip:</b> open the dedicated <b>Peak Lab</b> help tab for the full workflow.</li>
</ul>
<h3>MOVEMENT LAB</h3>
<ul>
  <li><b>Purpose:</b> label bounded movement windows, synchronize raw-video inspection with a graph cursor, count reviewed peaks inside each movement, and export movement-level metrics.</li>
  <li><b>Tip:</b> use the dedicated <b>Movement Lab</b> help tab for protocol, video, and MATLAB-export details.</li>
</ul>
<h3>COMPARE LAB</h3>
<ul>
  <li><b>Purpose:</b> manually combine traces from different dates, conditions, filters, bodyparts, or axes in one overlay.</li>
  <li><b>Trace label:</b> write the metadata you want shown in the legend, such as date + condition + filter.</li>
  <li><b>Trace palette:</b> Peak Lab and Compare Lab share exactly three final palettes: <b>Coral Grove</b>, <b>Orchid Dusk</b>, and <b>Aqua Current</b>.</li>
  <li><b>Export:</b> save the full figure as PNG, SVG, PDF, or interactive HTML. Static formats require kaleido.</li>
</ul>
""",
    "Peak Lab": HELP_STYLE + """
<h2>Peak Lab</h2>
<p><b>Recommended workflow:</b> LOAD CSV → choose detection signal → choose a working range → FIND PEAKS → review / move events → EXPORT.</p>
<p class="note">All left-side sections are collapsible <b>and the entire control column now scrolls vertically</b>, so multiple sections can stay open without being crushed.</p>
<h3>Signal / View</h3>
<ul>
  <li><b>Bodypart:</b> choose the structure whose XYZ coordinates are displayed.</li>
  <li><b>Primary axis:</b> this is the coordinate used by <b>FIND PEAKS</b>. Choose <b>None</b> when you only want to inspect multiple visible traces without designating a detection axis.</li>
  <li><b>Visible traces:</b> turn X, Y, and Z on/off independently.</li>
  <li><b>Trace layout:</b> choose Overlay, Separate XYZ, or Primary trace on top. Separate XYZ is the only multi-subplot mode; Primary trace on top keeps the original single-canvas view and draws the detection axis last/thicker so it stands out.</li>
  <li><b>Trace palette:</b> use the same named color sets available in Compare Lab.</li>
  <li><b>Hover details:</b> show frame, elapsed time, timestamp, and XYZ under the mouse.</li>
</ul>
<h3>Signal Cleanup</h3>
<ul>
  <li><b>Fill short internal gaps:</b> linearly fills only bounded NaN runs up to the selected maximum number of frames. Longer gaps stay missing, so Peak Lab does not invent long movement segments.</li>
  <li><b>Savitzky–Golay:</b> local polynomial smoothing that usually preserves peak location and shape better than simple averaging. It is useful for kinematic peak review, but its window/polyorder must be tuned and sharp outliers can create overshoot.</li>
  <li><b>Butterworth low-pass:</b> suppresses high-frequency tracking noise using a frequency cutoff. Peak timing is protected with zero-phase forward/backward filtering, but a cutoff that is too low can round or attenuate genuine fast movements.</li>
  <li><b>Show raw reference:</b> when cleanup is active, draw the raw primary trace as a faint dotted reference so you can see exactly what the cleaning changed.</li>
  <li><b>Important:</b> cleanup changes only Peak Lab's display/detection signal; the loaded raw XYZ columns are not overwritten.</li>
</ul>
<h3>Working Range</h3>
<ul>
  <li><b>Start / End:</b> the exact frame boundaries used for plotting <b>and peak detection</b>.</li>
  <li><b>SELECT RANGE ON PLOT:</b> drag a Plotly selection box; the x-boundaries are copied to Start/End even if the box does not intersect every visible trace.</li>
  <li><b>USE CURRENT ZOOM:</b> zoom normally with Plotly, then convert the visible x-range into the working range.</li>
  <li><b>Range summary:</b> shows frame/time boundaries, duration, and the number of kept peaks in the active signal.</li>
</ul>
<h3>Find Peaks</h3>
<ul>
  <li><b>Peak mode:</b> <b>Maximum (top)</b>, <b>Minimum (bottom)</b>, or <b>Both</b>.</li>
  <li><b>Auto prominence:</b> estimate prominence from only the current working range.</li>
  <li><b>Prominence / distance / width:</b> SciPy peak criteria applied to the active bodypart + primary axis.</li>
  <li><span class="action">FIND PEAKS:</span> creates a <b>draft</b> peak batch inside the current working range and replaces only an unconfirmed matching draft instead of duplicating it.</li>
  <li><span class="action">CONFIRM RANGE + CONTINUE:</span> lock the reviewed draft peaks into the working dataset, return to the full graph, and select another movement section. Confirmed peaks remain visible when you continue.</li>
  <li><b>DISCARD DRAFT:</b> remove only the unconfirmed batch for the current bodypart/axis/range.</li>
  <li><b>UNDO LAST:</b> restore the event dataset to the state before the most recent find/clear/confirm action.</li>
  <li><b>CLEAR THIS AXIS:</b> remove peaks for only the current bodypart + primary axis.</li>
  <li><b>Moon progress:</b> a moon-phase status plus wait cursor appears while Peak Lab is finding candidates, updating the table, or refreshing Plotly.</li>
</ul>
<h3>Manual Review</h3>
<ul>
  <li><b>Fast removal workflow:</b> keep <b>Hover details</b> on, use the peak marker to identify/select its EVENT DATASET row, then uncheck <b>keep</b> for a false peak. Unchecked rows stay visible in the dataset but are excluded from kept exports.</li>
  <li><b>Move a peak reliably:</b> select exactly one EVENT DATASET row, edit <b>MANUAL REVIEW → Frame</b>, then press <b>MOVE SELECTED PEAK</b>. Frame, elapsed time, timestamp, XYZ, and primary value update together.</li>
  <li><b>Add a missed event:</b> enter its frame and press <b>ADD MANUAL FRAME</b>. Manual events use a diamond marker and are confirmed automatically.</li>
  <li><b>Event index:</b> the chronological event number within the same <b>event label + bodypart + primary axis</b>. The table is automatically reordered by frame, so event indices now appear in chronological order instead of appended detection batches.</li>
  <li><b>Overlapping re-detection:</b> rerunning FIND PEAKS on an overlapping working range replaces overlapping draft auto-peaks for that same signal rather than stacking duplicate draft batches.</li>
</ul>
<h3>Export / review session</h3>
<ul>
  <li><b>✓ CONFIRM KEPT:</b> confirm every currently checked draft row from the EVENT DATASET. This is the easiest whole-table confirmation before export.</li>
  <li><b>3D velocity:</b> each exported event/timepoint row includes <code>velocity_3d</code>, the per-frame 3D movement rate calculated from consecutive XYZ samples and elapsed time.</li>
  <li><b>Review session:</b> SAVE SESSION stores the source, controls, trace layout/palette, current zoom, and reviewed events in a separate JSON file. Enable <b>Save review session with export</b> to write a companion JSON beside CSV/MAT automatically.</li>
  <li><span class="action">EXPORT KEPT CSV:</span> export checked <b>confirmed</b> events. Draft peaks stay in the session but are excluded until confirmed.</li>
  <li><span class="action">EXPORT KEPT MAT:</span> export the same confirmed kept event dataset as a MATLAB <code>.mat</code> struct.</li>
</ul>
""",
    "Compare Lab": HELP_STYLE + """
<h2>Compare Lab</h2>
<p>Compare Lab compares manually selected traces from different dates, conditions, filters, bodyparts, or coordinate axes.</p>
<h3>Add traces</h3>
<ul>
  <li><b>CSV:</b> choose any triangulated 3D CSV and press <b>READ SOURCE</b>.</li>
  <li><b>Trace label:</b> the app automatically looks two folders above the CSV for a session timestamp such as <code>20260731_111816</code>. You can still replace it with any name before adding the trace.</li>
  <li><b>Bodypart / Axis:</b> independently choose X, Y, or Z for each added trace.</li>
  <li><b>Start / End:</b> optionally restrict one source to a frame interval before adding it.</li>
  <li><span class="action">ADD TRACE TO COMPARISON:</span> append that source/axis to the Trace Set. Repeat with as many recordings as needed.</li>
</ul>
<h3>Plot design</h3>
<ul>
  <li><b>Plot mode — Overlay:</b> draw every trace on one shared graph.</li>
  <li><b>Plot mode — Stacked vertically:</b> place one recording per row with a shared X axis and a common true-value Y range, making consistency across sessions easier to inspect without normalizing the data.</li>
  <li><b>Y-axis label:</b> enter your own scientific/display label, for example <code>Left hand X position (mm)</code>.</li>
  <li><b>Show trace labels / legend:</b> show or hide the legend in Overlay mode; in Stacked mode this controls the date/session labels on the right edge of each row.</li>
  <li><b>X axis:</b> use original frame, elapsed seconds, or relative frame where each selected interval starts at zero.</li>
  <li><b>Trace palette:</b> choose one of the same named color sets used by Peak Lab.</li>
  <li><span class="action">UPDATE COMPARISON:</span> redraw the interactive Plotly figure from the current Trace Set.</li>
  <li><b>Resizable workspace:</b> drag the vertical divider between controls and plot. The left control panel now keeps a safe minimum width instead of being clipped underneath the Plotly pane.</li>
  <li><b>Important:</b> colors and vertical layout change presentation only; Compare Lab does not normalize, filter, or alter the coordinate values.</li>
</ul>
<h3>Export</h3>
<ul>
  <li><span class="action">EXPORT FULL FIGURE:</span> save the full Plotly figure as PNG, SVG, PDF, or interactive HTML. The default filename comes from <b>Graph title</b>. PNG/SVG/PDF require kaleido; HTML does not.</li>
</ul>
""",
    "Movement Lab": HELP_STYLE + """
<h2>Movement Lab</h2>
<p>Movement Lab sits one level above Peak Lab: Peak Lab identifies event points; Movement Lab labels <b>bounded movement episodes</b> and stores one row per movement.</p>
<h3>Movement protocol</h3>
<ul>
  <li><b>Protocol:</b> give the recording sequence a reusable name.</li>
  <li><b>Movement order:</b> enter one movement label per line. The first template item is <b>Shoulder flexion / extension</b>; the remaining placeholders are intentionally generic until you enter the lab's exact sequence.</li>
  <li><b>REMEMBER DEFAULT:</b> preserve the edited protocol across future drafts.</li>
  <li><b>ADD MOVEMENT WINDOW + NEXT:</b> stores the selected window and automatically advances to the next movement label; wrapping the sequence increments the set number.</li>
</ul>
<h3>Movement window</h3>
<ul>
  <li><b>SELECT WINDOW ON PLOT:</b> drag across one movement to define start/end frames.</li>
  <li><b>USE CURRENT ZOOM:</b> convert the current Plotly zoom into the movement boundary.</li>
  <li><b>Range summary:</b> reports frame/time boundaries, duration, and how many reviewed Peak Lab events fall inside the window.</li>
</ul>
<h3>Video inspection</h3>
<ul>
  <li><b>Raw videos:</b> the GUI first tries to match the recording ID from the loaded 3D CSV to the raw-video paths remembered from Triangulation. You can always browse manually to override it.</li>
  <li><b>Camera count:</b> controls which Cam-# choices appear in the floating inspector.</li>
  <li><span class="action">OPEN VIDEO INSPECTOR:</span> opens a separate Qt video window with a draggable seek bar, ±5 second jump controls, and 0.5×/1×/1.5×/2× playback speed.</li>
  <li><b>Track video:</b> playback time is mapped to the nearest CSV <code>time_seconds</code> sample when available, which keeps the vertical cursor stable and aligned to the 3D data.</li>
</ul>
<h3>Calculated movement fields</h3>
<ul>
  <li><b>Duration:</b> start/end elapsed time from the triangulated CSV.</li>
  <li><b>Peak count:</b> number of kept Peak Lab events inside the movement window.</li>
  <li><b>3D displacement / path length / velocity:</b> calculated from the selected bodypart's XYZ trajectory when enough finite samples exist.</li>
  <li><b>Signal extrema / phase order:</b> optional generic min/max timing such as <code>min→max</code>. This is <b>not automatically called anatomical flexion/extension</b> because that interpretation depends on body landmarks and coordinate conventions.</li>
  <li><b>Outcome:</b> optional Not scored / Success / Failure field for future reaching-task workflows.</li>
</ul>
<h3>Export</h3>
<ul>
  <li><span class="action">EXPORT CSV:</span> movement-level table for Python/R/spreadsheets.</li>
  <li><span class="action">EXPORT MAT:</span> the same movement-level dataset as a MATLAB <code>.mat</code> struct.</li>
</ul>
""",
}


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Motion Pipeline — Quick Help")
        self.resize(920, 680)

        root = QVBoxLayout(self)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the current help page…")
        find_button = QPushButton("FIND")
        find_button.clicked.connect(self.find_next)
        self.search.returnPressed.connect(self.find_next)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(find_button)
        root.addLayout(search_row)

        self.tabs = QTabWidget()
        self.browsers: dict[str, QTextBrowser] = {}
        for title, html in HELP_PAGES.items():
            page = QWidget()
            layout = QVBoxLayout(page)
            browser = QTextBrowser()
            browser.setOpenExternalLinks(False)
            browser.setHtml(html)
            layout.addWidget(browser)
            self.tabs.addTab(page, title)
            self.browsers[title] = browser
        root.addWidget(self.tabs, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("CLOSE")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        root.addLayout(close_row)

    def show_section(self, title: str):
        names = [self.tabs.tabText(i) for i in range(self.tabs.count())]
        if title in names:
            self.tabs.setCurrentIndex(names.index(title))
        self.show()
        self.raise_()
        self.activateWindow()

    def find_next(self):
        text = self.search.text().strip()
        if not text:
            return
        title = self.tabs.tabText(self.tabs.currentIndex())
        browser = self.browsers[title]
        if not browser.find(text):
            cursor = browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            browser.setTextCursor(cursor)
            browser.find(text)
