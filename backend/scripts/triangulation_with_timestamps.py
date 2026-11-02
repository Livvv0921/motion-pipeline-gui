r"""
Triangulate DeepLabCut 2D predictions into 3D coordinates with Aniposelib.

The script can process raw and optionally filtered DLC H5 files (median, ARIMA, Savitzky–Golay, Butterworth).
It validates camera files and bodyparts, reports frame counts and missing-data
statistics, asks for terminal confirmation, triangulates in chunks using the
stable OpenCV path (fast=True), saves checkpoints, and writes CSV/NPY outputs.

Run from Anaconda Prompt:
    conda activate aniposelib
    python triangulation.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import gc
import json
import sys
import traceback

import cv2
import numpy as np
import pandas as pd
from aniposelib.cameras import CameraGroup


# =============================================================================
# SETTINGS: edit this section
# =============================================================================

TRIAL_FOLDER = Path(
    r"Z:\root2\Animals2\Kimchi\Recording\Processed_Data\Passive"
    r"\Passive_20260731_111332"
)

CALIBRATION_PATH = Path(
    r"Z:\root2\Animals2\Kimchi\Recording\Processed_Data\Passive\Calibration"
    r"\Calibration_20260731_100436\calibration.toml"
)

# Choose one or more versions.
# Examples:
#     DATA_VERSIONS = ["raw"]
#     DATA_VERSIONS = ["median"]
#     DATA_VERSIONS = ["median", "arima"]
#     DATA_VERSIONS = ["raw"]
DATA_VERSIONS = ["raw"]

BODY_PARTS = ["Left_Hand", "Right_Hand"]

# One tuple per physical camera, in the same order used for calibration.
CAMERA_IDENTIFIERS = [
    ("Cam-0", "camera_0"),
    ("Cam-1", "camera_1"),
    ("Cam-2", "camera_2"),
    ("Cam-3", "camera_3"),
]

SCORE_THRESHOLD = 0.5
CHUNK_SIZE = 500

# Use OpenCV pairwise triangulation rather than the JAX path that previously
# destabilized the notebook kernel.
USE_FAST_TRIANGULATION = True
UNDISTORT_POINTS = True

ASK_BEFORE_TRIANGULATION = True
OVERWRITE_EXISTING_3D = False
SAVE_CHECKPOINT_AFTER_EACH_CHUNK = True

# All 3D products go in this subfolder inside TRIAL_FOLDER.
OUTPUT_SUBFOLDER = "3d"
OUTPUT_BASENAME = "left_hand_right_hand_3d"

# Timing metadata comes from the original MP4 recordings.
# By default the script looks for a raw folder with the same name as TRIAL_FOLDER.
RAW_VIDEO_ROOT = Path(
    r"Z:\root2\Animals2\Kimchi\Recording\Raw_Data\Video\Passive"
)
RAW_VIDEO_FOLDER: Path | None = None
VIDEO_EXTENSION = ".mp4"

# Small metadata differences such as 59.94 vs 59.9401 are okay.
FPS_TOLERANCE = 0.05


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def print_section(title: str) -> None:
    line = "=" * 78
    print(f"\n{line}\n{title}\n{line}", flush=True)


def ask_yes_no(question: str) -> bool:
    while True:
        response = input(f"{question} [y/n]: ").strip().lower()
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        print("Please enter y/yes or n/no.")


def bytes_to_mb(number: int) -> float:
    return number / (1024 ** 2)


def version_suffix(version: str) -> str | None:
    if version == "raw":
        return None
    if version in {"median", "arima", "savgol", "butterworth"}:
        return f"_{version}"
    raise ValueError(f"Unsupported data version: {version!r}")


def format_elapsed_timestamp(seconds: float) -> str:
    """Format elapsed seconds as MM:SS.mmm, or HH:MM:SS.mmm for long trials."""
    if not np.isfinite(seconds) or seconds < 0:
        return ""

    total_milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
    return f"{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def raw_video_folder() -> Path:
    """Resolve the raw recording folder used to obtain FPS/timing metadata."""
    folder = RAW_VIDEO_FOLDER or (RAW_VIDEO_ROOT / TRIAL_FOLDER.name)
    if not folder.is_dir():
        raise FileNotFoundError(
            "Raw video folder needed for timestamp metadata was not found:\n"
            f"{folder}\n\n"
            "Either make the raw and processed trial folder names match, or set "
            "RAW_VIDEO_FOLDER explicitly in the SETTINGS section."
        )
    return folder


def find_one_source_video(
    folder: Path,
    camera_identifiers: tuple[str, ...],
) -> Path:
    """Find exactly one original MP4 for a physical camera."""
    videos = sorted(folder.glob(f"*{VIDEO_EXTENSION}"))
    identifiers = tuple(text.lower() for text in camera_identifiers)
    matches = [
        path for path in videos
        if any(text in path.name.lower() for text in identifiers)
    ]

    if not matches:
        available = "\n".join(f"  - {p.name}" for p in videos) or "  (none)"
        raise FileNotFoundError(
            f"No source video matched camera identifiers {camera_identifiers}.\n"
            f"Folder searched: {folder}\nAvailable videos:\n{available}"
        )

    if len(matches) > 1:
        formatted = "\n".join(f"  - {p.name}" for p in matches)
        raise RuntimeError(
            f"More than one source video matched {camera_identifiers}:\n{formatted}\n"
            "Keep one intended video per camera or make CAMERA_IDENTIFIERS more specific."
        )

    return matches[0]


def read_video_timing_metadata() -> dict[str, object]:
    """Read FPS and frame count from each original camera video and validate them."""
    folder = raw_video_folder()
    source_videos = [
        find_one_source_video(folder, identifiers)
        for identifiers in CAMERA_IDENTIFIERS
    ]

    camera_timing: list[dict[str, object]] = []
    fps_values: list[float] = []
    frame_counts: list[int] = []

    print_section("SOURCE VIDEO TIMING")
    print("Raw video folder:", folder)

    for camera_index, video_path in enumerate(source_videos):
        capture = cv2.VideoCapture(str(video_path))
        try:
            if not capture.isOpened():
                raise RuntimeError(f"OpenCV could not open source video: {video_path}")
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            frame_count = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        finally:
            capture.release()

        if not np.isfinite(fps) or fps <= 0:
            raise RuntimeError(
                f"Invalid FPS ({fps}) read from source video: {video_path}"
            )
        if frame_count <= 0:
            raise RuntimeError(
                f"Invalid frame count ({frame_count}) read from source video: {video_path}"
            )

        fps_values.append(fps)
        frame_counts.append(frame_count)
        camera_timing.append({
            "camera_index": camera_index,
            "video": str(video_path),
            "fps": fps,
            "frame_count": frame_count,
        })
        print(
            f"  camera {camera_index}: {video_path.name} | "
            f"FPS={fps:.6f} | frames={frame_count:,}"
        )

    fps_min = min(fps_values)
    fps_max = max(fps_values)
    if fps_max - fps_min > FPS_TOLERANCE:
        raise RuntimeError(
            "Source camera FPS values differ more than allowed tolerance.\n"
            f"FPS values: {fps_values}\nTolerance: {FPS_TOLERANCE}"
        )

    fps_used = float(np.median(fps_values))
    print(f"\nFPS used for elapsed timestamps: {fps_used:.6f}")
    if len(set(frame_counts)) > 1:
        print(
            "WARNING: Source video frame counts differ: "
            f"{frame_counts}. Triangulation already trims DLC data to the shortest H5."
        )

    return {
        "raw_video_folder": str(folder),
        "fps_used": fps_used,
        "fps_values": fps_values,
        "source_frame_counts": frame_counts,
        "source_videos": [str(path) for path in source_videos],
        "cameras": camera_timing,
    }


def validate_settings() -> Path:
    if not TRIAL_FOLDER.is_dir():
        raise FileNotFoundError(
            f"Trial folder does not exist:\n{TRIAL_FOLDER}"
        )

    if not CALIBRATION_PATH.is_file():
        raise FileNotFoundError(
            f"Calibration TOML does not exist:\n{CALIBRATION_PATH}"
        )

    allowed = {"raw", "median", "arima", "savgol", "butterworth"}
    invalid = [version for version in DATA_VERSIONS if version not in allowed]
    if invalid:
        raise ValueError(
            f"Invalid DATA_VERSIONS: {invalid}. Allowed: {sorted(allowed)}"
        )

    if not DATA_VERSIONS:
        raise ValueError("DATA_VERSIONS is empty.")

    if len(DATA_VERSIONS) != len(set(DATA_VERSIONS)):
        raise ValueError("DATA_VERSIONS contains a duplicate.")

    if not 0 <= SCORE_THRESHOLD <= 1:
        raise ValueError("SCORE_THRESHOLD must be between 0 and 1.")

    if CHUNK_SIZE <= 0:
        raise ValueError("CHUNK_SIZE must be greater than zero.")

    if not BODY_PARTS:
        raise ValueError("BODY_PARTS is empty.")

    output_folder = TRIAL_FOLDER / OUTPUT_SUBFOLDER
    output_folder.mkdir(parents=True, exist_ok=True)
    return output_folder


# =============================================================================
# H5 DISCOVERY AND VALIDATION
# =============================================================================

def h5_belongs_to_version(path: Path, version: str) -> bool:
    stem = path.stem.lower()

    if version == "raw":
        return not stem.endswith(("_median", "_arima", "_savgol", "_butterworth", "_filtered"))

    return stem.endswith(f"_{version}")


def find_one_h5_for_camera(
    camera_identifiers: tuple[str, ...],
    version: str,
) -> Path:
    """Find exactly one H5 for one camera and one data version."""
    all_h5 = sorted(TRIAL_FOLDER.glob("*.h5"))
    identifiers = tuple(text.lower() for text in camera_identifiers)

    matches = [
        path
        for path in all_h5
        if any(text in path.name.lower() for text in identifiers)
        and h5_belongs_to_version(path, version)
    ]

    if not matches:
        available = "\n".join(f"  - {path.name}" for path in all_h5) or "  (none)"
        raise FileNotFoundError(
            f"No {version!r} H5 matched camera identifiers "
            f"{camera_identifiers}.\nFolder searched: {TRIAL_FOLDER}\n"
            f"Available H5 files:\n{available}"
        )

    if len(matches) > 1:
        formatted = "\n".join(f"  - {path.name}" for path in matches)
        raise RuntimeError(
            f"More than one {version!r} H5 matched camera identifiers "
            f"{camera_identifiers}:\n{formatted}\n"
            "Keep only one intended result or make CAMERA_IDENTIFIERS more specific."
        )

    return matches[0]


def select_h5_files(version: str) -> list[Path]:
    return [
        find_one_h5_for_camera(identifiers, version)
        for identifiers in CAMERA_IDENTIFIERS
    ]


def inspect_h5_structure(h5_path: Path) -> tuple[str, list[str], list[str]]:
    """Return scorer, available bodyparts, and available coordinate names."""
    df = pd.read_hdf(h5_path)
    try:
        if not isinstance(df.columns, pd.MultiIndex):
            raise ValueError(
                f"Expected DLC MultiIndex columns in {h5_path.name}, but got "
                f"{type(df.columns).__name__}."
            )

        level_names = list(df.columns.names)
        required_levels = {"scorer", "bodyparts", "coords"}
        if not required_levels.issubset(level_names):
            raise ValueError(
                f"H5 columns in {h5_path.name} do not contain expected levels "
                f"{sorted(required_levels)}. Found: {level_names}"
            )

        scorers = list(dict.fromkeys(df.columns.get_level_values("scorer")))
        if not scorers:
            raise ValueError(f"No scorer found in {h5_path.name}.")

        scorer = str(scorers[0])
        available_bodyparts = sorted(
            set(str(x) for x in df.columns.get_level_values("bodyparts"))
        )
        coords = sorted(set(str(x) for x in df.columns.get_level_values("coords")))
        return scorer, available_bodyparts, coords
    finally:
        del df


# =============================================================================
# LOAD AND SUMMARIZE 2D DATA
# =============================================================================

def load_2d_data(
    h5_files: list[Path],
) -> tuple[np.ndarray, np.ndarray, list[int], list[dict[str, object]]]:
    all_points: list[np.ndarray] = []
    all_scores: list[np.ndarray] = []
    frame_counts: list[int] = []
    camera_summaries: list[dict[str, object]] = []

    for camera_index, h5_path in enumerate(h5_files):
        print(f"\nLoading camera {camera_index}: {h5_path.name}", flush=True)
        df = pd.read_hdf(h5_path)

        try:
            scorer = str(df.columns.get_level_values("scorer")[0])
            available_bodyparts = set(
                str(x) for x in df.columns.get_level_values("bodyparts")
            )
            missing_bodyparts = [
                bodypart for bodypart in BODY_PARTS
                if bodypart not in available_bodyparts
            ]
            if missing_bodyparts:
                raise KeyError(
                    f"{h5_path.name} is missing bodyparts {missing_bodyparts}. "
                    f"Available: {sorted(available_bodyparts)}"
                )

            cam_points: list[np.ndarray] = []
            cam_scores: list[np.ndarray] = []
            bodypart_stats: dict[str, dict[str, float | int]] = {}

            for bodypart in BODY_PARTS:
                try:
                    xy = (
                        df[scorer][bodypart][["x", "y"]]
                        .to_numpy(dtype=np.float64)
                    )
                    likelihood = (
                        df[scorer][bodypart]["likelihood"]
                        .to_numpy(dtype=np.float64)
                    )
                except KeyError as exc:
                    raise KeyError(
                        f"Could not extract x, y, and likelihood for "
                        f"{bodypart!r} from {h5_path.name}."
                    ) from exc

                cam_points.append(xy)
                cam_scores.append(likelihood)
                bodypart_stats[bodypart] = {
                    "frames": int(len(likelihood)),
                    "mean_likelihood": float(np.nanmean(likelihood)),
                    "above_threshold": int(
                        np.count_nonzero(likelihood >= SCORE_THRESHOLD)
                    ),
                    "above_threshold_percent": float(
                        np.mean(likelihood >= SCORE_THRESHOLD) * 100
                    ),
                }

            camera_points = np.stack(cam_points, axis=1)
            camera_scores = np.stack(cam_scores, axis=1)

            all_points.append(camera_points)
            all_scores.append(camera_scores)
            frame_counts.append(camera_points.shape[0])
            camera_summaries.append(
                {
                    "camera_index": camera_index,
                    "file": str(h5_path),
                    "scorer": scorer,
                    "frames": int(camera_points.shape[0]),
                    "bodyparts": bodypart_stats,
                }
            )

            print("  scorer:       ", scorer)
            print("  frames:       ", camera_points.shape[0])
            print("  points shape: ", camera_points.shape)
            print("  scores shape: ", camera_scores.shape)
            for bodypart in BODY_PARTS:
                stats = bodypart_stats[bodypart]
                print(
                    f"  {bodypart}: mean likelihood="
                    f"{stats['mean_likelihood']:.3f}, >= {SCORE_THRESHOLD}="
                    f"{stats['above_threshold_percent']:.2f}%"
                )
        finally:
            del df

    n_frames = min(frame_counts)
    points = np.ascontiguousarray(
        np.stack([array[:n_frames] for array in all_points], axis=0),
        dtype=np.float64,
    )
    scores = np.ascontiguousarray(
        np.stack([array[:n_frames] for array in all_scores], axis=0),
        dtype=np.float64,
    )

    del all_points
    del all_scores
    gc.collect()

    return points, scores, frame_counts, camera_summaries


def summarize_before_triangulation(
    points: np.ndarray,
    scores: np.ndarray,
    frame_counts: list[int],
) -> tuple[np.ndarray, np.ndarray]:
    print_section("2D DATA SUMMARY")
    print("Frames per camera:")
    for index, frame_count in enumerate(frame_counts):
        print(f"  camera {index}: {frame_count:,}")

    if len(set(frame_counts)) > 1:
        print(
            "WARNING: Camera frame counts differ. All cameras will be trimmed "
            f"to the shortest length: {min(frame_counts):,} frames."
        )

    print("\nStacked points shape:", points.shape)
    print("Stacked scores shape:", scores.shape)
    print("Points dtype:        ", points.dtype)
    print("Points memory:       ", f"{bytes_to_mb(points.nbytes):.2f} MB")
    print("Scores memory:       ", f"{bytes_to_mb(scores.nbytes):.2f} MB")

    points_filtered = points.copy()
    points_filtered[scores < SCORE_THRESHOLD] = np.nan

    camera_counts = np.sum(
        np.isfinite(points_filtered[:, :, :, 0]),
        axis=0,
    )
    usable_mask = camera_counts >= 2

    print("\nLikelihood threshold:", SCORE_THRESHOLD)
    print(
        "All camera/bodypart detections above threshold:",
        f"{np.mean(scores >= SCORE_THRESHOLD) * 100:.2f}%",
    )
    print(
        "Frame/bodypart points visible in at least 2 cameras:",
        f"{int(usable_mask.sum()):,} / {usable_mask.size:,} "
        f"({usable_mask.mean() * 100:.2f}%)",
    )

    for bodypart_index, bodypart in enumerate(BODY_PARTS):
        percent = usable_mask[:, bodypart_index].mean() * 100
        print(f"  {bodypart}: {percent:.2f}% triangulatable")

    if not np.any(usable_mask):
        raise RuntimeError(
            "No bodypart has detections from at least two cameras. "
            "Triangulation cannot continue."
        )

    return points_filtered, usable_mask


# =============================================================================
# TRIANGULATION AND SAVING
# =============================================================================

def triangulate_version(
    version: str,
    cgroup: CameraGroup,
    output_folder: Path,
    timing_metadata: dict[str, object],
) -> dict[str, object]:
    print_section(f"DATA VERSION: {version.upper()}")

    h5_files = select_h5_files(version)
    print("Selected H5 files in camera order:")
    for index, h5_path in enumerate(h5_files):
        print(f"  camera {index}: {h5_path.name}")

    # Quick structural validation before loading every array.
    for h5_path in h5_files:
        scorer, available_bodyparts, coords = inspect_h5_structure(h5_path)
        missing = [bp for bp in BODY_PARTS if bp not in available_bodyparts]
        if missing:
            raise KeyError(
                f"{h5_path.name} is missing {missing}. "
                f"Available bodyparts: {available_bodyparts}"
            )
        if not {"x", "y", "likelihood"}.issubset(coords):
            raise KeyError(
                f"{h5_path.name} is missing required coordinate columns. "
                f"Found: {coords}"
            )

    points, scores, frame_counts, camera_summaries = load_2d_data(h5_files)
    points_filtered, usable_mask = summarize_before_triangulation(
        points,
        scores,
        frame_counts,
    )

    n_cameras, n_frames, n_bodyparts, n_xy = points_filtered.shape

    if n_xy != 2:
        raise ValueError(
            f"Expected final points dimension of 2 (x,y), got {n_xy}."
        )

    if n_cameras != len(cgroup.cameras):
        raise ValueError(
            f"2D data contains {n_cameras} cameras, but calibration contains "
            f"{len(cgroup.cameras)} cameras."
        )

    csv_path = output_folder / f"{version}_{OUTPUT_BASENAME}.csv"
    npy_path = output_folder / f"{version}_{OUTPUT_BASENAME}.npy"
    checkpoint_path = output_folder / f"{version}_p3ds_checkpoint.npy"
    report_path = output_folder / f"{version}_triangulation_report.json"

    existing_outputs = [path for path in (csv_path, npy_path) if path.exists()]
    if existing_outputs and not OVERWRITE_EXISTING_3D:
        paths = "\n".join(f"  - {path}" for path in existing_outputs)
        raise FileExistsError(
            "3D output already exists and OVERWRITE_EXISTING_3D is False:\n"
            f"{paths}"
        )

    print("\nPlanned outputs:")
    print("  CSV:       ", csv_path)
    print("  NPY:       ", npy_path)
    print("  checkpoint:", checkpoint_path)
    print("  report:    ", report_path)

    if ASK_BEFORE_TRIANGULATION and not ask_yes_no(
        f"Start triangulating the {version!r} data now?"
    ):
        print(f"Skipped {version!r} by user request.")
        return {
            "version": version,
            "status": "cancelled",
            "h5_files": [str(path) for path in h5_files],
        }

    started = datetime.now()
    p3ds = np.full(
        (n_frames, n_bodyparts, 3),
        np.nan,
        dtype=np.float64,
    )

    total_chunks = (n_frames + CHUNK_SIZE - 1) // CHUNK_SIZE
    print_section(f"TRIANGULATING {version.upper()}")

    for chunk_number, start_frame in enumerate(
        range(0, n_frames, CHUNK_SIZE),
        start=1,
    ):
        end_frame = min(start_frame + CHUNK_SIZE, n_frames)
        chunk_frames = end_frame - start_frame
        percent = end_frame / n_frames * 100

        print(
            f"Chunk {chunk_number}/{total_chunks}: frames "
            f"{start_frame:,}-{end_frame - 1:,} / {n_frames:,} "
            f"({percent:.1f}%)",
            flush=True,
        )

        chunk = points_filtered[:, start_frame:end_frame, :, :]
        chunk_flat = np.ascontiguousarray(
            chunk.reshape(n_cameras, chunk_frames * n_bodyparts, 2),
            dtype=np.float64,
        )

        result_flat = cgroup.triangulate(
            chunk_flat,
            undistort=UNDISTORT_POINTS,
            fast=USE_FAST_TRIANGULATION,
        )
        result_chunk = result_flat.reshape(chunk_frames, n_bodyparts, 3)
        result_chunk[~usable_mask[start_frame:end_frame]] = np.nan
        p3ds[start_frame:end_frame] = result_chunk

        if SAVE_CHECKPOINT_AFTER_EACH_CHUNK:
            np.save(checkpoint_path, p3ds)

    ended = datetime.now()

    # -------------------------------------------------------------------------
    # Attach frame/time metadata to every 3D row.
    # Frame 0 is defined as elapsed time 0.000 s.
    # -------------------------------------------------------------------------
    fps_used = float(timing_metadata["fps_used"])
    source_frame_counts = [int(x) for x in timing_metadata["source_frame_counts"]]
    if n_frames > min(source_frame_counts):
        print(
            "WARNING: Triangulated frame count is larger than at least one source "
            "video frame count. Check synchronization/video metadata."
        )

    frame_numbers = np.arange(n_frames, dtype=np.int64)
    time_seconds = frame_numbers.astype(np.float64) / fps_used
    timestamps = [format_elapsed_timestamp(value) for value in time_seconds]

    out = pd.DataFrame({
        "frame": frame_numbers,
        "time_seconds": time_seconds,
        "timestamp": timestamps,
    })
    for bodypart_index, bodypart in enumerate(BODY_PARTS):
        out[f"{bodypart}_x"] = p3ds[:, bodypart_index, 0]
        out[f"{bodypart}_y"] = p3ds[:, bodypart_index, 1]
        out[f"{bodypart}_z"] = p3ds[:, bodypart_index, 2]

    out.to_csv(csv_path, index=False)
    np.save(npy_path, p3ds)

    bodypart_3d_stats: dict[str, object] = {}
    print_section(f"3D DATA SUMMARY: {version.upper()}")
    print("Final p3ds shape:", p3ds.shape)
    print("Final p3ds dtype:", p3ds.dtype)
    print("Final p3ds memory:", f"{bytes_to_mb(p3ds.nbytes):.2f} MB")

    for bodypart_index, bodypart in enumerate(BODY_PARTS):
        finite_xyz = np.all(np.isfinite(p3ds[:, bodypart_index, :]), axis=1)
        valid_count = int(finite_xyz.sum())
        missing_count = int(n_frames - valid_count)
        valid_percent = float(finite_xyz.mean() * 100)
        bodypart_3d_stats[bodypart] = {
            "valid_frames": valid_count,
            "missing_frames": missing_count,
            "valid_percent": valid_percent,
        }
        print(
            f"  {bodypart}: valid={valid_count:,}, missing={missing_count:,}, "
            f"valid={valid_percent:.2f}%"
        )

    print("\nCSV shape:", out.shape)
    print("CSV missing values by column:")
    for column, missing_count in out.isna().sum().items():
        print(
            f"  {column}: {missing_count:,} "
            f"({missing_count / len(out) * 100:.2f}%)"
        )

    report: dict[str, object] = {
        "version": version,
        "status": "completed",
        "started": started.isoformat(),
        "ended": ended.isoformat(),
        "elapsed_seconds": (ended - started).total_seconds(),
        "trial_folder": str(TRIAL_FOLDER),
        "calibration_path": str(CALIBRATION_PATH),
        "calibration_camera_names": list(cgroup.get_names()),
        "h5_files": [str(path) for path in h5_files],
        "bodyparts": BODY_PARTS,
        "score_threshold": SCORE_THRESHOLD,
        "chunk_size": CHUNK_SIZE,
        "fast_triangulation": USE_FAST_TRIANGULATION,
        "frame_counts_before_trimming": frame_counts,
        "frames_used": n_frames,
        "timing": {
            **timing_metadata,
            "duration_seconds": float((n_frames - 1) / fps_used) if n_frames else 0.0,
            "first_timestamp": timestamps[0] if timestamps else None,
            "last_timestamp": timestamps[-1] if timestamps else None,
        },
        "points_shape": list(points.shape),
        "scores_shape": list(scores.shape),
        "p3ds_shape": list(p3ds.shape),
        "triangulatable_percent": float(usable_mask.mean() * 100),
        "camera_summaries": camera_summaries,
        "bodypart_3d_stats": bodypart_3d_stats,
        "csv_path": str(csv_path),
        "npy_path": str(npy_path),
        "checkpoint_path": str(checkpoint_path),
    }

    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nSaved CSV:   ", csv_path)
    print("Saved NPY:   ", npy_path)
    print("Saved report:", report_path)
    print("Elapsed:     ", ended - started)

    del points
    del scores
    del points_filtered
    del usable_mask
    del p3ds
    del out
    gc.collect()

    return report


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    print_section("ANIPOSELIB TRIANGULATION PIPELINE")
    print("[PROGRESS 2%] Starting triangulation", flush=True)
    output_folder = validate_settings()
    print("[PROGRESS 7%] Triangulation settings validated", flush=True)

    print("Trial folder:       ", TRIAL_FOLDER)
    print("Calibration TOML:   ", CALIBRATION_PATH)
    print("Output folder:      ", output_folder)
    print("Data versions:      ", DATA_VERSIONS)
    print("Bodyparts:          ", BODY_PARTS)
    print("Score threshold:    ", SCORE_THRESHOLD)
    print("Chunk size:         ", CHUNK_SIZE)
    print("Fast triangulation: ", USE_FAST_TRIANGULATION)

    timing_metadata = read_video_timing_metadata()
    print("[PROGRESS 12%] Source video timing loaded", flush=True)

    cgroup = CameraGroup.load(str(CALIBRATION_PATH))
    print("\nCalibration loaded successfully.")
    print("Calibration cameras:", cgroup.get_names())
    print("Number of cameras:  ", len(cgroup.cameras))
    print("[PROGRESS 18%] Calibration loaded", flush=True)

    if len(cgroup.cameras) != len(CAMERA_IDENTIFIERS):
        raise ValueError(
            f"Calibration contains {len(cgroup.cameras)} cameras, but "
            f"CAMERA_IDENTIFIERS defines {len(CAMERA_IDENTIFIERS)} cameras."
        )

    all_reports: list[dict[str, object]] = []
    failures = 0

    total_versions = max(1, len(DATA_VERSIONS))
    for version_index, version in enumerate(DATA_VERSIONS, start=1):
        start_percent = 18 + int((version_index - 1) / total_versions * 72)
        print(f"[PROGRESS {start_percent}%] Triangulating {version}", flush=True)
        try:
            report = triangulate_version(
                version, cgroup, output_folder, timing_metadata
            )
            all_reports.append(report)
        except Exception:
            failures += 1
            print_section(f"FAILED DATA VERSION: {version.upper()}")
            traceback.print_exc()
            print(
                f"\nThe {version!r} version failed. Other selected versions "
                "will still be attempted."
            )
        done_percent = 18 + int(version_index / total_versions * 72)
        print(f"[PROGRESS {done_percent}%] Finished {version_index}/{total_versions} data version(s)", flush=True)

    print("[PROGRESS 95%] Writing triangulation report", flush=True)
    batch_report_path = output_folder / "triangulation_batch_report.json"
    batch_report_path.write_text(
        json.dumps(
            {
                "created": datetime.now().isoformat(),
                "trial_folder": str(TRIAL_FOLDER),
                "calibration_path": str(CALIBRATION_PATH),
                "timing_metadata": timing_metadata,
                "requested_versions": DATA_VERSIONS,
                "failures": failures,
                "reports": all_reports,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print_section("TRIANGULATION PIPELINE FINISHED")
    print("Completed/cancelled versions:", len(all_reports))
    print("Failed versions:             ", failures)
    print("Batch report:                ", batch_report_path)
    print("[PROGRESS 100%] Triangulation pipeline finished", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nTriangulation interrupted by user.")
        raise SystemExit(130)
    except Exception:
        print_section("TRIANGULATION PIPELINE FAILED")
        traceback.print_exc()
        raise SystemExit(1)
