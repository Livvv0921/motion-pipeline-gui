r"""
Analyze selected passive-recording folders with DeepLabCut.

Folder behavior
---------------
Raw videos remain under VIDEO_ROOT. DeepLabCut analysis outputs are written to
PROCESS_ROOT using the exact same recording-folder name, for example:

Raw input:
    ...\Raw_Data\Video\Passive\Kimchi_Passive_20260605_123548\*.mp4

Processed output:
    ...\Processed_Data\Passive\Kimchi_Passive_20260605_123548\*.h5

Optional filtering
------------------
Choose one or more filters in FILTER_TYPES.

Both filters:
    FILTER_TYPES = ["median", "arima"]

Median only:
    FILTER_TYPES = ["median"]

ARIMA only:
    FILTER_TYPES = ["arima"]

No filtering:
    APPLY_FILTERS = False

DeepLabCut normally writes every filtered result with "_filtered" in the
filename. This script immediately renames each result to "_median" or
"_arima", allowing both filtered versions to remain in the same folder while
preserving the original raw DLC prediction file.
"""

from datetime import datetime
from pathlib import Path
import traceback

import deeplabcut
import numpy as np
import pandas as pd
from scipy.signal import butter, savgol_filter, sosfiltfilt


# -----------------------------------------------------------------------------
# SETTINGS: edit these values as needed
# -----------------------------------------------------------------------------

CONFIG_PATH = Path(
    r"C:\Users\NMRC\OneDrive\Desktop\Kimchi Model\Kimchi-Passive-410C-Devyn-2026-05-27\config.yaml"
)

# Root containing the original recording folders and MP4 files.
VIDEO_ROOT = Path(
    r"Z:\root2\Animals2\Kimchi\Recording\Raw_Data\Video\Passive"
)

# Root where DLC outputs will be stored.
# Each source folder gets a matching folder here automatically.
PROCESS_ROOT = Path(
    r"Z:\root2\Animals2\Kimchi\Recording\Processed_Data\Passive"
)

# Enter the exact source-folder names to analyze.
FOLDERS_TO_ANALYZE = [
    "Passive_20260731_111332",
    # "Passive_20260519_123334",
]

SHUFFLE = 4
VIDEO_EXTENSION = ".mp4"

# False: keep and reuse an existing raw DLC .h5 result.
# True: call analyze_videos again even when a raw result is already present.
REANALYZE_EXISTING = False


# -----------------------------------------------------------------------------
# OPTIONAL DLC FILTERING
# -----------------------------------------------------------------------------

# Set to False when you do not want any filtered outputs.
APPLY_FILTERS = False

# Select any filters. The GUI defaults to no filters selected.
# DLC-native: median, arima
# Additional experimental 2D coordinate filters: savgol, butterworth
FILTER_TYPES = []

# False: keep and reuse an existing filter-specific output.
# True: recreate the selected filter outputs.
REFILTER_EXISTING = False

# Median-filter setting: must be an odd positive integer, e.g. 3, 5, 7.
MEDIAN_WINDOW_LENGTH = 5

# ARIMA settings. These are ignored when ARIMA is not selected.
ARIMA_P_BOUND = 0.001
ARIMA_AR_DEGREE = 3
ARIMA_MA_DEGREE = 1
ARIMA_ALPHA = 0.01

# Savitzky–Golay settings for 2D x/y coordinates.
SAVGOL_WINDOW_LENGTH = 11
SAVGOL_POLYORDER = 2

# Butterworth low-pass settings for 2D x/y coordinates. Video FPS is read
# directly from each source video; 60 Hz is used only if FPS cannot be read.
BUTTERWORTH_CUTOFF_HZ = 6.0
BUTTERWORTH_ORDER = 4
BUTTERWORTH_FPS_FALLBACK = 60.0

# Keep False unless you also want CSV copies in addition to H5 files.
SAVE_RAW_AS_CSV = False
SAVE_FILTERED_AS_CSV = False


# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------

def output_folder_for(video_path: Path) -> Path:
    """Return/create the processed folder matching the source folder name."""
    destination = PROCESS_ROOT / video_path.parent.name
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def all_matching_h5_files(video_path: Path, destination: Path) -> list[Path]:
    """Return every H5 output in destination belonging to one video."""
    return sorted(destination.glob(f"{video_path.stem}*.h5"))


def matching_raw_h5_files(video_path: Path, destination: Path) -> list[Path]:
    """Return raw DLC H5 outputs, excluding every filtered variant."""
    filtered_suffixes = ("_filtered", "_median", "_arima", "_savgol", "_butterworth")

    return [
        path
        for path in all_matching_h5_files(video_path, destination)
        if not path.stem.endswith(filtered_suffixes)
    ]


def matching_named_filter_files(
    video_path: Path,
    destination: Path,
    filter_type: str,
    extension: str,
) -> list[Path]:
    """Return saved filter-specific outputs such as *_median.h5."""
    return sorted(
        destination.glob(f"{video_path.stem}*_{filter_type}{extension}")
    )


def matching_temporary_filter_files(
    video_path: Path,
    destination: Path,
    extension: str,
) -> list[Path]:
    """Return DLC's temporary outputs ending in *_filtered.h5 or CSV."""
    return sorted(destination.glob(f"{video_path.stem}*_filtered{extension}"))


def collect_selected_videos() -> list[Path]:
    """Collect videos only from folders named in FOLDERS_TO_ANALYZE."""
    selected_videos: list[Path] = []

    for folder_name in FOLDERS_TO_ANALYZE:
        source_folder = VIDEO_ROOT / folder_name

        if not source_folder.is_dir():
            print(f"WARNING: Folder not found, skipping: {source_folder}")
            continue

        folder_videos = sorted(source_folder.glob(f"*{VIDEO_EXTENSION}"))

        if not folder_videos:
            print(
                f"WARNING: No {VIDEO_EXTENSION} videos found in: "
                f"{source_folder}"
            )
            continue

        destination = PROCESS_ROOT / folder_name
        destination.mkdir(parents=True, exist_ok=True)

        print(f"Found {len(folder_videos)} video(s) in {folder_name}")
        print(f"Outputs will go to: {destination}")

        selected_videos.extend(folder_videos)

    return selected_videos


def validate_settings() -> None:
    """Fail early when paths or filter settings are invalid."""
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")

    if not VIDEO_ROOT.is_dir():
        raise FileNotFoundError(f"Video root folder not found: {VIDEO_ROOT}")

    if not FOLDERS_TO_ANALYZE:
        raise ValueError(
            "FOLDERS_TO_ANALYZE is empty. Add at least one folder name."
        )

    PROCESS_ROOT.mkdir(parents=True, exist_ok=True)

    if APPLY_FILTERS:
        if not FILTER_TYPES:
            raise ValueError(
                "APPLY_FILTERS is True, but FILTER_TYPES is empty. "
                "Choose at least one supported filter."
            )

        allowed_filters = {"median", "arima", "savgol", "butterworth"}
        invalid_filters = [
            filter_type
            for filter_type in FILTER_TYPES
            if filter_type not in allowed_filters
        ]

        if invalid_filters:
            raise ValueError(
                "FILTER_TYPES may contain only median, arima, savgol, and/or butterworth. "
                f"Invalid value(s): {invalid_filters}"
            )

        if len(FILTER_TYPES) != len(set(FILTER_TYPES)):
            raise ValueError(
                "FILTER_TYPES contains a duplicate. List each filter only once."
            )

        if "median" in FILTER_TYPES and (
            MEDIAN_WINDOW_LENGTH <= 0
            or MEDIAN_WINDOW_LENGTH % 2 == 0
        ):
            raise ValueError(
                "MEDIAN_WINDOW_LENGTH must be a positive odd integer."
            )

        if "savgol" in FILTER_TYPES:
            if SAVGOL_WINDOW_LENGTH < 3 or SAVGOL_WINDOW_LENGTH % 2 == 0:
                raise ValueError("SAVGOL_WINDOW_LENGTH must be an odd integer >= 3.")
            if SAVGOL_POLYORDER < 1 or SAVGOL_POLYORDER >= SAVGOL_WINDOW_LENGTH:
                raise ValueError("SAVGOL_POLYORDER must be >= 1 and smaller than SAVGOL_WINDOW_LENGTH.")

        if "butterworth" in FILTER_TYPES:
            if BUTTERWORTH_CUTOFF_HZ <= 0:
                raise ValueError("BUTTERWORTH_CUTOFF_HZ must be greater than zero.")
            if BUTTERWORTH_ORDER < 1:
                raise ValueError("BUTTERWORTH_ORDER must be >= 1.")


def analyze_one_video(video_path: Path, destination: Path) -> tuple[Path, bool]:
    """
    Analyze one video if needed.

    Returns:
        (raw_h5_path, created_new_raw_output)
    """
    existing_raw = matching_raw_h5_files(video_path, destination)

    if existing_raw and not REANALYZE_EXISTING:
        print(f"Raw analysis already exists: {existing_raw[-1].name}")
        return existing_raw[-1], False

    deeplabcut.analyze_videos(
        str(CONFIG_PATH),
        [str(video_path)],
        shuffle=SHUFFLE,
        videotype=VIDEO_EXTENSION,
        save_as_csv=SAVE_RAW_AS_CSV,
        destfolder=str(destination),
    )

    new_raw = matching_raw_h5_files(video_path, destination)

    if not new_raw:
        raise RuntimeError(
            "DeepLabCut finished without creating a matching raw .h5 file "
            f"in {destination}."
        )

    return new_raw[-1], True


def rename_temporary_filter_outputs(
    video_path: Path,
    destination: Path,
    filter_type: str,
) -> Path:
    """
    Rename DLC's generic *_filtered output to a filter-specific filename.

    For example:
        *_filtered.h5 -> *_median.h5
        *_filtered.h5 -> *_arima.h5
    """
    temporary_h5_files = matching_temporary_filter_files(
        video_path,
        destination,
        ".h5",
    )

    if not temporary_h5_files:
        raise RuntimeError(
            "DeepLabCut filtering finished without creating a matching "
            f"*_filtered.h5 file in {destination}."
        )

    temporary_h5 = temporary_h5_files[-1]
    final_h5 = temporary_h5.with_name(
        temporary_h5.name.replace(
            "_filtered.h5",
            f"_{filter_type}.h5",
        )
    )

    if final_h5.exists():
        if REFILTER_EXISTING:
            final_h5.unlink()
        else:
            raise FileExistsError(
                f"Filter output already exists and refiltering is disabled: {final_h5}"
            )

    temporary_h5.rename(final_h5)

    # If CSV output was requested, rename its generic _filtered file too.
    if SAVE_FILTERED_AS_CSV:
        temporary_csv_files = matching_temporary_filter_files(
            video_path,
            destination,
            ".csv",
        )

        if temporary_csv_files:
            temporary_csv = temporary_csv_files[-1]
            final_csv = temporary_csv.with_name(
                temporary_csv.name.replace(
                    "_filtered.csv",
                    f"_{filter_type}.csv",
                )
            )

            if final_csv.exists():
                if REFILTER_EXISTING:
                    final_csv.unlink()
                else:
                    raise FileExistsError(
                        "Filter CSV already exists and refiltering is disabled: "
                        f"{final_csv}"
                    )

            temporary_csv.rename(final_csv)

    return final_h5


def _contiguous_finite_segments(values: np.ndarray):
    finite = np.isfinite(values)
    indices = np.flatnonzero(finite)
    if not len(indices):
        return
    splits = np.where(np.diff(indices) > 1)[0] + 1
    for segment in np.split(indices, splits):
        if len(segment):
            yield segment


def _savgol_segments(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float).copy()
    for idx in _contiguous_finite_segments(arr):
        segment = arr[idx]
        if len(segment) < 3:
            continue
        window = min(
            int(SAVGOL_WINDOW_LENGTH),
            len(segment) if len(segment) % 2 == 1 else len(segment) - 1,
        )
        min_window = int(SAVGOL_POLYORDER) + 2
        if min_window % 2 == 0:
            min_window += 1
        if window < min_window or window < 3:
            continue
        arr[idx] = savgol_filter(
            segment,
            window_length=window,
            polyorder=min(int(SAVGOL_POLYORDER), window - 1),
            mode="interp",
        )
    return arr


def _video_fps(video_path: Path) -> float:
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        cap.release()
        if np.isfinite(fps) and fps > 0:
            return fps
    except Exception:
        pass
    print(
        f"WARNING: Could not read FPS from {video_path.name}; "
        f"using fallback {BUTTERWORTH_FPS_FALLBACK:g} Hz."
    )
    return float(BUTTERWORTH_FPS_FALLBACK)


def _butterworth_segments(values: np.ndarray, fs: float) -> np.ndarray:
    arr = np.asarray(values, dtype=float).copy()
    nyquist = fs / 2.0
    cutoff = min(max(float(BUTTERWORTH_CUTOFF_HZ), 1e-6), nyquist * 0.95)
    sos = butter(int(BUTTERWORTH_ORDER), cutoff, btype="lowpass", fs=fs, output="sos")
    for idx in _contiguous_finite_segments(arr):
        segment = arr[idx]
        if len(segment) < max(12, int(BUTTERWORTH_ORDER) * 4):
            continue
        try:
            arr[idx] = sosfiltfilt(sos, segment)
        except ValueError:
            continue
    return arr


def custom_filter_one_video(
    raw_h5: Path,
    video_path: Path,
    destination: Path,
    filter_type: str,
) -> tuple[Path, bool]:
    """Create/reuse Savitzky–Golay or Butterworth filtered DLC H5 output."""
    existing = matching_named_filter_files(video_path, destination, filter_type, ".h5")
    if existing and not REFILTER_EXISTING:
        print(f"{filter_type.capitalize()} result already exists: {existing[-1].name}")
        return existing[-1], False

    final_h5 = raw_h5.with_name(f"{raw_h5.stem}_{filter_type}.h5")
    if final_h5.exists():
        if REFILTER_EXISTING:
            final_h5.unlink()
        else:
            return final_h5, False

    df = pd.read_hdf(raw_h5)
    if not isinstance(df.columns, pd.MultiIndex) or "coords" not in df.columns.names:
        raise ValueError(f"Expected DLC MultiIndex columns with a 'coords' level in {raw_h5.name}.")

    fps = _video_fps(video_path) if filter_type == "butterworth" else None
    coords_level = df.columns.names.index("coords")
    out = df.copy()
    changed = 0
    for column in df.columns:
        coord = str(column[coords_level]).lower()
        if coord not in {"x", "y"}:
            continue
        values = pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)
        if filter_type == "savgol":
            filtered = _savgol_segments(values)
        elif filter_type == "butterworth":
            filtered = _butterworth_segments(values, float(fps))
        else:
            raise ValueError(f"Unsupported custom filter: {filter_type}")
        out[column] = filtered
        changed += 1

    if changed == 0:
        raise ValueError(f"No x/y coordinate columns were found in {raw_h5.name}.")

    out.to_hdf(final_h5, key="df_with_missing", mode="w", format="table")
    if SAVE_FILTERED_AS_CSV:
        out.to_csv(final_h5.with_suffix(".csv"), index=True)
    return final_h5, True


def filter_one_video(
    video_path: Path,
    destination: Path,
    filter_type: str,
    raw_h5: Path,
) -> tuple[Path, bool]:
    """
    Create or reuse one named filtered DLC result.

    Returns:
        (filter_h5_path, created_new_filter_output)
    """
    if filter_type in {"savgol", "butterworth"}:
        return custom_filter_one_video(raw_h5, video_path, destination, filter_type)

    existing_named_filter = matching_named_filter_files(
        video_path,
        destination,
        filter_type,
        ".h5",
    )

    if existing_named_filter and not REFILTER_EXISTING:
        print(
            f"{filter_type.capitalize()} result already exists: "
            f"{existing_named_filter[-1].name}"
        )
        return existing_named_filter[-1], False

    # Remove a stale generic temporary output before starting this filter.
    # This prevents accidentally renaming a leftover file from an older run.
    for stale_path in matching_temporary_filter_files(
        video_path,
        destination,
        ".h5",
    ):
        stale_path.unlink()

    if SAVE_FILTERED_AS_CSV:
        for stale_path in matching_temporary_filter_files(
            video_path,
            destination,
            ".csv",
        ):
            stale_path.unlink()

    filter_arguments = {
        "config": str(CONFIG_PATH),
        "video": [str(video_path)],
        "videotype": VIDEO_EXTENSION,
        "shuffle": SHUFFLE,
        "filtertype": filter_type,
        "save_as_csv": SAVE_FILTERED_AS_CSV,
        "destfolder": str(destination),
    }

    if filter_type == "median":
        filter_arguments["windowlength"] = MEDIAN_WINDOW_LENGTH

    elif filter_type == "arima":
        filter_arguments.update(
            {
                "p_bound": ARIMA_P_BOUND,
                "ARdegree": ARIMA_AR_DEGREE,
                "MAdegree": ARIMA_MA_DEGREE,
                "alpha": ARIMA_ALPHA,
            }
        )

    deeplabcut.filterpredictions(**filter_arguments)

    final_h5 = rename_temporary_filter_outputs(
        video_path,
        destination,
        filter_type,
    )

    return final_h5, True


# -----------------------------------------------------------------------------
# MAIN PIPELINE
# -----------------------------------------------------------------------------

def main() -> None:
    print("[PROGRESS 2%] Validating passive-analysis settings", flush=True)
    validate_settings()
    videos = collect_selected_videos()
    print("[PROGRESS 5%] Recordings discovered", flush=True)

    if not videos:
        raise FileNotFoundError(
            "No videos were found in the selected folders. "
            "Check VIDEO_ROOT and FOLDERS_TO_ANALYZE."
        )

    log_path = PROCESS_ROOT / "dlc_passive_batch_log.txt"

    analyzed_count = 0
    reused_raw_count = 0
    filtered_count = 0
    reused_filtered_count = 0
    failed_count = 0

    with log_path.open("a", encoding="utf-8") as log:
        start_time = datetime.now()

        log.write(
            f"\n\nBatch started: {start_time.isoformat()}\n"
            f"Selected folders: {FOLDERS_TO_ANALYZE}\n"
            f"Videos found: {len(videos)}\n"
            f"Processed root: {PROCESS_ROOT}\n"
            f"Reanalyze existing: {REANALYZE_EXISTING}\n"
            f"Apply filters: {APPLY_FILTERS}\n"
            f"Filter types: {FILTER_TYPES if APPLY_FILTERS else 'disabled'}\n"
            f"Refilter existing: {REFILTER_EXISTING}\n"
        )

        for number, video_path in enumerate(videos, start=1):
            destination = output_folder_for(video_path)

            header = (
                f"\n[{number}/{len(videos)}] {video_path.name}\n"
                f"    Source: {video_path}\n"
                f"    Output: {destination}"
            )
            print(header)
            log.write(header + "\n")
            log.flush()

            try:
                raw_h5, raw_created = analyze_one_video(
                    video_path,
                    destination,
                )

                if raw_created:
                    analyzed_count += 1
                    raw_status = "ANALYZED"
                else:
                    reused_raw_count += 1
                    raw_status = "REUSED RAW"

                raw_message = f"    {raw_status}: {raw_h5.name}"
                print(raw_message)
                log.write(raw_message + "\n")

                if APPLY_FILTERS:
                    for filter_type in FILTER_TYPES:
                        filtered_h5, filter_created = filter_one_video(
                            video_path,
                            destination,
                            filter_type,
                            raw_h5,
                        )

                        if filter_created:
                            filtered_count += 1
                            filter_status = "FILTERED"
                        else:
                            reused_filtered_count += 1
                            filter_status = "REUSED FILTERED"

                        filter_message = (
                            f"    {filter_status} ({filter_type}): "
                            f"{filtered_h5.name}"
                        )
                        print(filter_message)
                        log.write(filter_message + "\n")

            except Exception:
                failed_count += 1
                error_text = traceback.format_exc()

                print(f"FAILED: {video_path}")
                print(error_text)

                log.write(f"FAILED: {video_path}\n")
                log.write(error_text + "\n")

            log.flush()
            percent = 5 + int(number / len(videos) * 90)
            print(f"[PROGRESS {percent}%] Finished {number}/{len(videos)} video(s)", flush=True)

        end_time = datetime.now()
        summary = (
            f"\nBatch ended: {end_time.isoformat()}\n"
            f"New raw analyses: {analyzed_count}\n"
            f"Reused raw analyses: {reused_raw_count}\n"
            f"New filtered analyses: {filtered_count}\n"
            f"Reused filtered analyses: {reused_filtered_count}\n"
            f"Failed: {failed_count}\n"
        )
        log.write(summary)

    print("\nFinished.")
    print(f"New raw analyses:       {analyzed_count}")
    print(f"Reused raw analyses:    {reused_raw_count}")
    print(f"New filtered analyses:  {filtered_count}")
    print(f"Reused filtered files:  {reused_filtered_count}")
    print(f"Failed:                 {failed_count}")
    print("Log:", log_path)
    print("[PROGRESS 100%] Passive analysis finished", flush=True)


if __name__ == "__main__":
    main()
