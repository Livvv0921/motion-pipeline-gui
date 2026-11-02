r"""
Create static Matplotlib PNG figures and interactive Plotly HTML figures from
triangulated 3D CSV files.

Expected triangulation outputs:
    TRIAL_FOLDER\3d\raw_left_hand_right_hand_3d.csv
    TRIAL_FOLDER\3d\median_left_hand_right_hand_3d.csv
    TRIAL_FOLDER\3d\arima_left_hand_right_hand_3d.csv

The Plotly HTML files are interactive: zoom, pan, hover over exact frames and
elapsed timestamps, toggle traces from the legend, and inspect 3D trajectories
by rotating them. The triangulated CSV is expected to contain frame,
time_seconds, and timestamp columns written by triangulation_with_timestamps.py.

Run:
    conda activate aniposelib
    python visualization_plotly.py

If Plotly is not installed:
    python -m pip install plotly
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import traceback

import matplotlib

# Keep the stable file-only Matplotlib backend.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go
except ImportError as exc:
    raise ImportError(
        "Plotly is not installed in this Python environment.\n"
        "Install it with:\n"
        "    python -m pip install plotly"
    ) from exc


# =============================================================================
# SETTINGS: edit this section
# =============================================================================

TRIAL_FOLDER = Path(
    r"Z:\root2\Animals2\Kimchi\Recording\Processed_Data\Passive"
    r"\Passive_20260731_111332"
)

THREED_SUBFOLDER = "3d"
FIGURE_SUBFOLDER = "figures"
CSV_BASENAME = "left_hand_right_hand_3d"

# Plot one or more triangulation versions.
# Examples:
#     ["raw"]
#     ["median"]
#     ["raw", "median", "arima"]
VERSIONS_TO_PLOT = ["raw"]

BODY_PARTS = ["Left_Hand", "Right_Hand"]

# -----------------------------------------------------------------------------
# OUTPUT TYPES
# -----------------------------------------------------------------------------

# Keep publication/QC PNGs if wanted.
CREATE_MATPLOTLIB_PNG = True

# Create interactive Plotly HTML files.
CREATE_PLOTLY_HTML = True

# True makes each HTML self-contained and usable offline.
# The files are larger, but another person can open them without internet.
PLOTLY_INCLUDE_JS = True

# -----------------------------------------------------------------------------
# FIGURE TYPES
# -----------------------------------------------------------------------------

# X/Y/Z comparison: Left and Right hand on the same graph.
CREATE_AXIS_COMPARISON_PLOTS = True

# One coordinate per graph.
CREATE_SINGLE_TRACE_PLOTS = True
SINGLE_TRACE_COLUMNS = [
    "Left_Hand_x",
    "Left_Hand_y",
    "Left_Hand_z",
    "Right_Hand_x",
    "Right_Hand_y",
    "Right_Hand_z",
]

# One graph per bodypart containing X, Y, and Z together.
# This is especially useful interactively because hovermode='x unified'
# shows all three coordinates for the same frame.
CREATE_XYZ_COMBINED_PLOTS = True

# One 3D trajectory per bodypart.
CREATE_3D_TRAJECTORY_PLOTS = True

# -----------------------------------------------------------------------------
# PLOTTING SETTINGS
# -----------------------------------------------------------------------------

# Reduce visual density without changing the saved 3D data.
# 1 = every frame. For interactive QC, keeping 1 is usually useful.
PLOT_EVERY_NTH_FRAME = 1

FIGURE_DPI = 200
LINE_WIDTH = 0.8
OVERWRITE_EXISTING_FIGURES = True

# Interactive 2D plots can include a small overview/range slider under the plot.
PLOTLY_SHOW_RANGE_SLIDER = True

# Hover precision for coordinate values.
PLOTLY_HOVER_DECIMALS = 3

# Choose what appears on the horizontal axis for both PNG and Plotly 2D plots.
# "frame" is recommended for QC because it maps directly back to the video.
# "time" shows elapsed seconds instead. Hover always shows BOTH frame and time.
X_AXIS_MODE = "frame"


# =============================================================================
# HELPERS
# =============================================================================

def print_section(title: str) -> None:
    line = "=" * 78
    print(f"\n{line}\n{title}\n{line}", flush=True)


def validate_settings() -> tuple[Path, Path]:
    if not TRIAL_FOLDER.is_dir():
        raise FileNotFoundError(f"Trial folder does not exist:\n{TRIAL_FOLDER}")

    if PLOT_EVERY_NTH_FRAME <= 0:
        raise ValueError("PLOT_EVERY_NTH_FRAME must be greater than zero.")

    if X_AXIS_MODE not in {"frame", "time"}:
        raise ValueError("X_AXIS_MODE must be either 'frame' or 'time'.")

    allowed = {"raw", "median", "arima", "savgol", "butterworth"}
    invalid = [version for version in VERSIONS_TO_PLOT if version not in allowed]
    if invalid:
        raise ValueError(
            f"Invalid VERSIONS_TO_PLOT: {invalid}. Allowed: {sorted(allowed)}"
        )

    if not VERSIONS_TO_PLOT:
        raise ValueError("VERSIONS_TO_PLOT is empty.")

    data_folder = TRIAL_FOLDER / THREED_SUBFOLDER
    if not data_folder.is_dir():
        raise FileNotFoundError(
            "3D data folder does not exist:\n"
            f"{data_folder}\nRun triangulation.py first."
        )

    figure_root = TRIAL_FOLDER / FIGURE_SUBFOLDER
    figure_root.mkdir(parents=True, exist_ok=True)
    return data_folder, figure_root


def should_skip(path: Path) -> bool:
    if path.exists() and not OVERWRITE_EXISTING_FIGURES:
        print("Skipping existing output:", path)
        return True
    return False


def save_matplotlib_figure(fig: plt.Figure, path: Path) -> None:
    if should_skip(path):
        plt.close(fig)
        return

    print("Saving PNG:", path, flush=True)
    fig.savefig(path, dpi=FIGURE_DPI)
    plt.close(fig)
    print("Saved PNG successfully.", flush=True)


def save_plotly_figure(fig: go.Figure, path: Path) -> None:
    if should_skip(path):
        return

    print("Saving interactive HTML:", path, flush=True)
    fig.write_html(
        str(path),
        include_plotlyjs=PLOTLY_INCLUDE_JS,
        full_html=True,
        auto_open=False,
    )
    print("Saved interactive HTML successfully.", flush=True)


def load_and_validate_csv(csv_path: Path) -> pd.DataFrame:
    if not csv_path.is_file():
        raise FileNotFoundError(f"3D CSV was not found:\n{csv_path}")

    df = pd.read_csv(csv_path)
    coordinate_columns = {
        f"{bodypart}_{axis}"
        for bodypart in BODY_PARTS
        for axis in ("x", "y", "z")
    }
    timing_columns = {"frame", "time_seconds", "timestamp"}

    missing_coordinates = sorted(coordinate_columns.difference(df.columns))
    if missing_coordinates:
        raise KeyError(
            f"CSV is missing required coordinate columns {missing_coordinates}.\n"
            f"Available columns: {list(df.columns)}"
        )

    missing_timing = sorted(timing_columns.difference(df.columns))
    if missing_timing:
        raise KeyError(
            "CSV is missing timing columns "
            f"{missing_timing}.\n"
            "Run the updated triangulation script so the 3D CSV contains "
            "frame, time_seconds, and timestamp."
        )

    for column in coordinate_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["frame"] = pd.to_numeric(df["frame"], errors="raise").astype(np.int64)
    df["time_seconds"] = pd.to_numeric(df["time_seconds"], errors="raise")
    df["timestamp"] = df["timestamp"].astype(str)

    if df["frame"].duplicated().any():
        raise ValueError("The CSV contains duplicate frame numbers.")
    if not df["frame"].is_monotonic_increasing:
        raise ValueError("Frame numbers are not monotonically increasing.")
    if not df["time_seconds"].is_monotonic_increasing:
        raise ValueError("time_seconds is not monotonically increasing.")

    return df


def print_data_summary(version: str, df: pd.DataFrame) -> dict[str, object]:
    print_section(f"DATA SUMMARY: {version.upper()}")
    print("Rows/frames:", f"{len(df):,}")
    print("Columns:    ", list(df.columns))
    print("Memory:     ", f"{df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

    if len(df):
        print("First frame: ", int(df["frame"].iloc[0]))
        print("Last frame:  ", int(df["frame"].iloc[-1]))
        print("First time:  ", df["timestamp"].iloc[0])
        print("Last time:   ", df["timestamp"].iloc[-1])
        print("Duration (s):", f"{df['time_seconds'].iloc[-1]:.3f}")

    summary: dict[str, object] = {
        "version": version,
        "frames": int(len(df)),
        "columns": list(df.columns),
        "timing": {
            "first_frame": int(df["frame"].iloc[0]) if len(df) else None,
            "last_frame": int(df["frame"].iloc[-1]) if len(df) else None,
            "first_timestamp": str(df["timestamp"].iloc[0]) if len(df) else None,
            "last_timestamp": str(df["timestamp"].iloc[-1]) if len(df) else None,
            "duration_seconds": float(df["time_seconds"].iloc[-1]) if len(df) else 0.0,
        },
        "missing": {},
        "ranges": {},
    }

    coordinate_columns = [
        f"{bodypart}_{axis}"
        for bodypart in BODY_PARTS
        for axis in ("x", "y", "z")
    ]

    for column in coordinate_columns:
        values = df[column].to_numpy(dtype=np.float64)
        finite = values[np.isfinite(values)]
        missing_count = int(np.count_nonzero(~np.isfinite(values)))
        missing_percent = (
            float(missing_count / len(values) * 100) if len(values) else 0.0
        )

        if finite.size:
            minimum = float(np.min(finite))
            maximum = float(np.max(finite))
            median = float(np.median(finite))
        else:
            minimum = maximum = median = float("nan")

        print(
            f"  {column}: missing={missing_count:,} ({missing_percent:.2f}%), "
            f"min={minimum:.3f}, median={median:.3f}, max={maximum:.3f}"
        )
        summary["missing"][column] = {
            "count": missing_count,
            "percent": missing_percent,
        }
        summary["ranges"][column] = {
            "min": minimum,
            "median": median,
            "max": maximum,
        }

    return summary


def sampled_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return only the frames requested for visualization."""
    return df.iloc[::PLOT_EVERY_NTH_FRAME]


def x_values(df: pd.DataFrame) -> np.ndarray:
    if X_AXIS_MODE == "frame":
        return df["frame"].to_numpy(dtype=np.int64)
    return df["time_seconds"].to_numpy(dtype=np.float64)


def x_axis_label() -> str:
    return "Frame" if X_AXIS_MODE == "frame" else "Elapsed time (seconds)"


def hover_customdata(df: pd.DataFrame) -> np.ndarray:
    """Columns: frame, display timestamp, elapsed seconds."""
    return np.column_stack(
        [
            df["frame"].to_numpy(dtype=np.int64),
            df["timestamp"].astype(str).to_numpy(),
            df["time_seconds"].to_numpy(dtype=np.float64),
        ]
    )


def plotly_hover_prefix() -> str:
    return (
        "Frame: %{customdata[0]}<br>"
        "Time: %{customdata[1]}<br>"
        "Elapsed: %{customdata[2]:.3f} s<br>"
    )


def plotly_2d_layout(fig: go.Figure, title: str, y_title: str) -> None:
    fig.update_layout(
        title=title,
        xaxis_title=x_axis_label(),
        yaxis_title=y_title,
        hovermode="x unified",
        template="plotly_white",
        legend_title_text="Trace",
    )

    fig.update_xaxes(
        rangeslider_visible=PLOTLY_SHOW_RANGE_SLIDER,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
    )
    fig.update_yaxes(showspikes=True)


# =============================================================================
# MATPLOTLIB STATIC PLOTS
# =============================================================================

def create_axis_comparison_png(
    version: str,
    df: pd.DataFrame,
    axis_name: str,
    output_folder: Path,
) -> None:
    plot_df = sampled_df(df)
    fig, ax = plt.subplots(figsize=(12, 5))

    for bodypart in BODY_PARTS:
        column = f"{bodypart}_{axis_name}"
        ax.plot(
            x_values(plot_df),
            plot_df[column].to_numpy(),
            label=column,
            linewidth=LINE_WIDTH,
        )

    ax.set_xlabel(x_axis_label())
    ax.set_ylabel(f"{axis_name.upper()} position")
    ax.set_title(
        f"{version.capitalize()} 3D {axis_name.upper()} position across frames"
    )
    ax.legend()

    save_matplotlib_figure(
        fig,
        output_folder / f"{version}_3d_{axis_name}_trajectory.png",
    )


def create_single_trace_png(
    version: str,
    df: pd.DataFrame,
    column: str,
    output_folder: Path,
) -> None:
    if column not in df.columns:
        raise KeyError(f"Requested single trace {column!r} is not present in the CSV.")

    plot_df = sampled_df(df)
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        x_values(plot_df),
        plot_df[column].to_numpy(),
        label=column,
        linewidth=LINE_WIDTH,
    )
    ax.set_xlabel(x_axis_label())
    ax.set_ylabel("3D position")
    ax.set_title(f"{version.capitalize()} single trace: {column}")
    ax.legend()

    save_matplotlib_figure(
        fig,
        output_folder / f"{version}_single_trace_{column}.png",
    )


def create_3d_trajectory_png(
    version: str,
    df: pd.DataFrame,
    bodypart: str,
    output_folder: Path,
) -> None:
    plot_df = sampled_df(df)
    x = plot_df[f"{bodypart}_x"].to_numpy(dtype=np.float64)
    y = plot_df[f"{bodypart}_y"].to_numpy(dtype=np.float64)
    z = plot_df[f"{bodypart}_z"].to_numpy(dtype=np.float64)
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)

    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot(x[valid], y[valid], z[valid], linewidth=LINE_WIDTH)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    ax.set_title(f"{version.capitalize()} 3D trajectory: {bodypart}")

    save_matplotlib_figure(
        fig,
        output_folder / f"{version}_3d_trajectory_{bodypart}.png",
    )


# =============================================================================
# PLOTLY INTERACTIVE PLOTS
# =============================================================================

def create_axis_comparison_html(
    version: str,
    df: pd.DataFrame,
    axis_name: str,
    output_folder: Path,
) -> None:
    plot_df = sampled_df(df)
    x_axis = x_values(plot_df)
    customdata = hover_customdata(plot_df)
    fig = go.Figure()

    for bodypart in BODY_PARTS:
        column = f"{bodypart}_{axis_name}"
        fig.add_trace(
            go.Scattergl(
                x=x_axis,
                y=plot_df[column].to_numpy(),
                customdata=customdata,
                mode="lines",
                name=column,
                connectgaps=False,
                hovertemplate=(
                    plotly_hover_prefix()
                    + f"{column}: %{{y:.{PLOTLY_HOVER_DECIMALS}f}}"
                    + "<extra></extra>"
                ),
            )
        )

    plotly_2d_layout(
        fig,
        title=f"{version.capitalize()} 3D {axis_name.upper()} position across frames",
        y_title=f"{axis_name.upper()} position",
    )

    save_plotly_figure(
        fig,
        output_folder / f"{version}_3d_{axis_name}_trajectory_interactive.html",
    )


def create_single_trace_html(
    version: str,
    df: pd.DataFrame,
    column: str,
    output_folder: Path,
) -> None:
    if column not in df.columns:
        raise KeyError(f"Requested single trace {column!r} is not present in the CSV.")

    plot_df = sampled_df(df)
    x_axis = x_values(plot_df)
    customdata = hover_customdata(plot_df)

    fig = go.Figure(
        data=[
            go.Scattergl(
                x=x_axis,
                y=plot_df[column].to_numpy(),
                customdata=customdata,
                mode="lines",
                name=column,
                connectgaps=False,
                hovertemplate=(
                    plotly_hover_prefix()
                    + f"{column}: %{{y:.{PLOTLY_HOVER_DECIMALS}f}}"
                    + "<extra></extra>"
                ),
            )
        ]
    )

    plotly_2d_layout(
        fig,
        title=f"{version.capitalize()} single trace: {column}",
        y_title="3D position",
    )

    save_plotly_figure(
        fig,
        output_folder / f"{version}_single_trace_{column}_interactive.html",
    )


def create_xyz_combined_html(
    version: str,
    df: pd.DataFrame,
    bodypart: str,
    output_folder: Path,
) -> None:
    """Interactive X/Y/Z traces for one bodypart on one shared frame axis."""
    plot_df = sampled_df(df)
    x_axis = x_values(plot_df)
    customdata = hover_customdata(plot_df)
    fig = go.Figure()

    for axis_name in ("x", "y", "z"):
        column = f"{bodypart}_{axis_name}"
        fig.add_trace(
            go.Scattergl(
                x=x_axis,
                y=plot_df[column].to_numpy(),
                customdata=customdata,
                mode="lines",
                name=axis_name.upper(),
                connectgaps=False,
                hovertemplate=(
                    plotly_hover_prefix()
                    + f"{axis_name.upper()}: %{{y:.{PLOTLY_HOVER_DECIMALS}f}}"
                    + "<extra></extra>"
                ),
            )
        )

    plotly_2d_layout(
        fig,
        title=f"{version.capitalize()} {bodypart}: X/Y/Z across frames",
        y_title="3D position",
    )

    save_plotly_figure(
        fig,
        output_folder / f"{version}_{bodypart}_XYZ_interactive.html",
    )


def create_3d_trajectory_html(
    version: str,
    df: pd.DataFrame,
    bodypart: str,
    output_folder: Path,
) -> None:
    plot_df = sampled_df(df)
    customdata = hover_customdata(plot_df)
    x = plot_df[f"{bodypart}_x"].to_numpy(dtype=np.float64)
    y = plot_df[f"{bodypart}_y"].to_numpy(dtype=np.float64)
    z = plot_df[f"{bodypart}_z"].to_numpy(dtype=np.float64)

    # Plotly can handle gaps, but filtering the fully invalid 3D rows makes the
    # hover data cleaner while still preserving frame numbers via customdata.
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)

    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=x[valid],
                y=y[valid],
                z=z[valid],
                customdata=customdata[valid],
                mode="lines",
                name=bodypart,
                hovertemplate=(
                    plotly_hover_prefix()
                    + f"X: %{{x:.{PLOTLY_HOVER_DECIMALS}f}}<br>"
                    f"Y: %{{y:.{PLOTLY_HOVER_DECIMALS}f}}<br>"
                    f"Z: %{{z:.{PLOTLY_HOVER_DECIMALS}f}}"
                    "<extra></extra>"
                ),
            )
        ]
    )

    fig.update_layout(
        title=f"{version.capitalize()} 3D trajectory: {bodypart}",
        template="plotly_white",
        scene=dict(
            xaxis_title="X",
            yaxis_title="Y",
            zaxis_title="Z",
        ),
    )

    save_plotly_figure(
        fig,
        output_folder / f"{version}_3d_trajectory_{bodypart}_interactive.html",
    )


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    print_section("3D VISUALIZATION PIPELINE")
    print("[PROGRESS 2%] Starting visualization", flush=True)
    data_folder, figure_root = validate_settings()
    print("[PROGRESS 8%] Visualization settings validated", flush=True)
    reports: list[dict[str, object]] = []
    failures = 0

    print("Trial folder:          ", TRIAL_FOLDER)
    print("3D data folder:        ", data_folder)
    print("Figure root:           ", figure_root)
    print("Versions to plot:      ", VERSIONS_TO_PLOT)
    print("Every nth frame:       ", PLOT_EVERY_NTH_FRAME)
    print("2D x-axis mode:        ", X_AXIS_MODE)
    print("Create PNG:            ", CREATE_MATPLOTLIB_PNG)
    print("Create Plotly HTML:    ", CREATE_PLOTLY_HTML)
    print("Matplotlib backend:    ", matplotlib.get_backend())

    total_versions = max(1, len(VERSIONS_TO_PLOT))
    for version_index, version in enumerate(VERSIONS_TO_PLOT, start=1):
        start_percent = 8 + int((version_index - 1) / total_versions * 82)
        print(f"[PROGRESS {start_percent}%] Visualizing {version}", flush=True)
        try:
            print_section(f"VISUALIZING VERSION: {version.upper()}")
            csv_path = data_folder / f"{version}_{CSV_BASENAME}.csv"
            output_version_name = "unfiltered" if version == "raw" else version
            version_root = figure_root / output_version_name
            static_folder = version_root / "static"
            interactive_folder = version_root / "interactive"

            if CREATE_MATPLOTLIB_PNG:
                static_folder.mkdir(parents=True, exist_ok=True)
            if CREATE_PLOTLY_HTML:
                interactive_folder.mkdir(parents=True, exist_ok=True)

            print("Loading:", csv_path)
            df = load_and_validate_csv(csv_path)
            summary = print_data_summary(version, df)
            summary["csv_path"] = str(csv_path)
            summary["static_folder"] = str(static_folder)
            summary["interactive_folder"] = str(interactive_folder)

            # -------------------------------------------------------------
            # X / Y / Z comparison plots
            # -------------------------------------------------------------
            if CREATE_AXIS_COMPARISON_PLOTS:
                for axis_name in ("x", "y", "z"):
                    if CREATE_MATPLOTLIB_PNG:
                        create_axis_comparison_png(
                            version,
                            df,
                            axis_name,
                            static_folder,
                        )
                    if CREATE_PLOTLY_HTML:
                        create_axis_comparison_html(
                            version,
                            df,
                            axis_name,
                            interactive_folder,
                        )

            # -------------------------------------------------------------
            # Single coordinate traces
            # -------------------------------------------------------------
            if CREATE_SINGLE_TRACE_PLOTS:
                for column in SINGLE_TRACE_COLUMNS:
                    if CREATE_MATPLOTLIB_PNG:
                        create_single_trace_png(
                            version,
                            df,
                            column,
                            static_folder,
                        )
                    if CREATE_PLOTLY_HTML:
                        create_single_trace_html(
                            version,
                            df,
                            column,
                            interactive_folder,
                        )

            # -------------------------------------------------------------
            # X/Y/Z combined per bodypart (Plotly)
            # -------------------------------------------------------------
            if CREATE_XYZ_COMBINED_PLOTS and CREATE_PLOTLY_HTML:
                for bodypart in BODY_PARTS:
                    create_xyz_combined_html(
                        version,
                        df,
                        bodypart,
                        interactive_folder,
                    )

            # -------------------------------------------------------------
            # 3D trajectories
            # -------------------------------------------------------------
            if CREATE_3D_TRAJECTORY_PLOTS:
                for bodypart in BODY_PARTS:
                    if CREATE_MATPLOTLIB_PNG:
                        create_3d_trajectory_png(
                            version,
                            df,
                            bodypart,
                            static_folder,
                        )
                    if CREATE_PLOTLY_HTML:
                        create_3d_trajectory_html(
                            version,
                            df,
                            bodypart,
                            interactive_folder,
                        )

            reports.append(summary)
            del df

        except Exception:
            failures += 1
            print_section(f"VISUALIZATION FAILED: {version.upper()}")
            traceback.print_exc()
            print(
                f"\nThe {version!r} visualization stage failed. Other selected "
                "versions will still be attempted."
            )
        done_percent = 8 + int(version_index / total_versions * 82)
        print(f"[PROGRESS {done_percent}%] Finished {version_index}/{total_versions} visualization version(s)", flush=True)

    print("[PROGRESS 95%] Writing visualization report", flush=True)
    report_path = figure_root / "visualization_report.json"
    report_path.write_text(
        json.dumps(
            {
                "created": datetime.now().isoformat(),
                "trial_folder": str(TRIAL_FOLDER),
                "versions_requested": VERSIONS_TO_PLOT,
                "create_matplotlib_png": CREATE_MATPLOTLIB_PNG,
                "create_plotly_html": CREATE_PLOTLY_HTML,
                "x_axis_mode": X_AXIS_MODE,
                "failures": failures,
                "reports": reports,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print_section("VISUALIZATION FINISHED")
    print("Successful versions:", len(reports))
    print("Failed versions:    ", failures)
    print("Visualization report:", report_path)

    if CREATE_PLOTLY_HTML:
        print(
            "\nInteractive Plotly files are .html files. Open them in a web "
            "browser to zoom, pan, hover over exact frames/timestamps, and rotate 3D plots."
        )

    print("[PROGRESS 100%] Visualization pipeline finished", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nVisualization interrupted by user.")
        raise SystemExit(130)
    except Exception:
        print_section("VISUALIZATION PIPELINE FAILED")
        traceback.print_exc()
        raise SystemExit(1)
