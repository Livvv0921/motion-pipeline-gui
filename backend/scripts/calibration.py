r"""
Create and save an Aniposelib camera calibration for one calibration recording.

The calibration videos remain in Raw_Data. The resulting calibration.toml and
log are written under CALIBRATION_OUTPUT_ROOT using the exact same source-folder
name.

Example
-------
Source:
    ...\Raw_Data\Video\Calibration\Calibration_20260716_094229\*.mp4

Output:
    ...\Processed_Data\Calibration\Calibration_20260716_094229\calibration.toml

Run from Anaconda Prompt:
    conda activate aniposelib
    python calibration.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import traceback

from aniposelib.boards import CharucoBoard
from aniposelib.cameras import CameraGroup


# =============================================================================
# SETTINGS: edit this section
# =============================================================================

CALIBRATION_VIDEO_FOLDER = Path(
    r"Z:\root2\Animals2\Kimchi\Recording\Raw_Data\Video\Calibration"
    r"\Calibration_20260731_100436"
)

CALIBRATION_OUTPUT_ROOT = Path(
    r"Z:\root2\Animals2\Kimchi\Recording\Processed_Data\Passive\Calibration"
)

VIDEO_EXTENSION = ".mp4"

# One camera definition per physical camera, in calibration/triangulation order.
# Each tuple contains acceptable text fragments for that camera's filename.
CAMERA_IDENTIFIERS = [
    ("Cam-0", "camera_0"),
    ("Cam-1", "camera_1"),
    ("Cam-2", "camera_2"),
    ("Cam-3", "camera_3"),
]

# Names stored inside calibration.toml. Their ORDER matters most.
CALIBRATION_CAMERA_NAMES = ["Cam-0", "Cam-1", "Cam-2", "Cam-3"]

# These values must match the physical ChArUco board.
CHARUCO_COLUMNS = 10
CHARUCO_ROWS = 8
SQUARE_LENGTH = 25.0
MARKER_LENGTH = 18.75
MARKER_BITS = 4
DICTIONARY_SIZE = 50

FISHEYE = True

# False protects an existing calibration.toml from accidental replacement.
RECALIBRATE_EXISTING = False

# Ask for terminal confirmation after all validation succeeds.
ASK_BEFORE_CALIBRATION = True


# =============================================================================
# HELPERS
# =============================================================================

def print_section(title: str) -> None:
    line = "=" * 78
    print(f"\n{line}\n{title}\n{line}", flush=True)


def ask_yes_no(question: str) -> bool:
    """Return True only after an explicit y/yes response."""
    while True:
        response = input(f"{question} [y/n]: ").strip().lower()
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        print("Please enter y/yes or n/no.")


def find_one_camera_video(
    folder: Path,
    identifiers: tuple[str, ...],
) -> Path:
    """Find exactly one calibration video for one camera."""
    all_videos = sorted(folder.glob(f"*{VIDEO_EXTENSION}"))
    lowered_identifiers = tuple(text.lower() for text in identifiers)

    matches = [
        path
        for path in all_videos
        if any(text in path.name.lower() for text in lowered_identifiers)
    ]

    if not matches:
        raise FileNotFoundError(
            "No calibration video matched camera identifiers "
            f"{identifiers}.\nFolder searched: {folder}"
        )

    if len(matches) > 1:
        formatted = "\n".join(f"  - {path.name}" for path in matches)
        raise RuntimeError(
            "More than one calibration video matched camera identifiers "
            f"{identifiers}:\n{formatted}\n"
            "Remove/rename extra files or make CAMERA_IDENTIFIERS more specific."
        )

    return matches[0]


def validate_settings() -> tuple[list[Path], Path, Path]:
    """Validate paths/settings and return videos, output folder, TOML path."""
    if not CALIBRATION_VIDEO_FOLDER.is_dir():
        raise FileNotFoundError(
            "Calibration video folder does not exist:\n"
            f"{CALIBRATION_VIDEO_FOLDER}"
        )

    if len(CAMERA_IDENTIFIERS) != len(CALIBRATION_CAMERA_NAMES):
        raise ValueError(
            "CAMERA_IDENTIFIERS and CALIBRATION_CAMERA_NAMES must have the "
            "same number of entries."
        )

    if MARKER_LENGTH >= SQUARE_LENGTH:
        raise ValueError("MARKER_LENGTH must be smaller than SQUARE_LENGTH.")

    videos = [
        find_one_camera_video(CALIBRATION_VIDEO_FOLDER, identifiers)
        for identifiers in CAMERA_IDENTIFIERS
    ]

    output_folder = CALIBRATION_OUTPUT_ROOT / CALIBRATION_VIDEO_FOLDER.name
    output_folder.mkdir(parents=True, exist_ok=True)
    calibration_path = output_folder / "calibration.toml"

    return videos, output_folder, calibration_path


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    started = datetime.now()
    print_section("ANIPOSELIB CALIBRATION")
    print("Started:", started.isoformat(timespec="seconds"), flush=True)
    print("[PROGRESS 2%] Starting calibration", flush=True)

    videos, output_folder, calibration_path = validate_settings()
    print("[PROGRESS 12%] Calibration inputs validated", flush=True)
    log_path = output_folder / "calibration_log.txt"

    print("\nCalibration source folder:", CALIBRATION_VIDEO_FOLDER)
    print("Calibration output folder:", output_folder)
    print("Calibration TOML path:    ", calibration_path)

    print("\nCamera order selected:")
    for index, (camera_name, video_path) in enumerate(
        zip(CALIBRATION_CAMERA_NAMES, videos),
        start=1,
    ):
        size_mb = video_path.stat().st_size / (1024 ** 2)
        print(
            f"  {index}. {camera_name:<10} -> {video_path.name} "
            f"({size_mb:.1f} MB)"
        )

    print("\nBoard definition:")
    print(f"  squares:       {CHARUCO_COLUMNS} × {CHARUCO_ROWS}")
    print(f"  square length: {SQUARE_LENGTH}")
    print(f"  marker length: {MARKER_LENGTH}")
    print(f"  marker bits:   {MARKER_BITS}")
    print(f"  dictionary:    {DICTIONARY_SIZE}")
    print(f"  fisheye:       {FISHEYE}")

    if calibration_path.exists() and not RECALIBRATE_EXISTING:
        print(
            "\nCalibration already exists and RECALIBRATE_EXISTING is False."
        )
        print("Existing file preserved:", calibration_path)
        print("Nothing was recalibrated.")
        print("[PROGRESS 100%] Existing calibration preserved", flush=True)
        return 0

    if calibration_path.exists():
        print("\nWARNING: Existing calibration will be replaced:")
        print(calibration_path)

    if ASK_BEFORE_CALIBRATION and not ask_yes_no(
        "Validation passed. Start camera calibration now?"
    ):
        print("Calibration cancelled by user.")
        return 0

    board = CharucoBoard(
        CHARUCO_COLUMNS,
        CHARUCO_ROWS,
        square_length=SQUARE_LENGTH,
        marker_length=MARKER_LENGTH,
        marker_bits=MARKER_BITS,
        dict_size=DICTIONARY_SIZE,
    )

    cgroup = CameraGroup.from_names(
        CALIBRATION_CAMERA_NAMES,
        fisheye=FISHEYE,
    )

    # Aniposelib expects one list per camera; each list may contain one or more
    # calibration videos for that camera.
    calibration_videos = [[str(path)] for path in videos]

    print_section("CALIBRATION RUNNING")
    print("[PROGRESS 25%] ChArUco detection / camera optimization started", flush=True)
    print(
        "Aniposelib is detecting the ChArUco board and optimizing camera "
        "parameters. This may take time.",
        flush=True,
    )

    error, rows = cgroup.calibrate_videos(calibration_videos, board)

    print("\nCalibration optimization finished.", flush=True)
    print("Calibration error:", error, flush=True)
    print("[PROGRESS 85%] Camera optimization finished", flush=True)

    cgroup.dump(str(calibration_path))
    print("[PROGRESS 95%] calibration.toml saved", flush=True)

    if not calibration_path.is_file():
        raise RuntimeError(
            "Calibration completed, but calibration.toml was not created."
        )

    ended = datetime.now()
    elapsed = ended - started

    with log_path.open("a", encoding="utf-8") as log:
        log.write(
            f"\nCalibration started: {started.isoformat()}\n"
            f"Calibration ended:   {ended.isoformat()}\n"
            f"Elapsed:             {elapsed}\n"
            f"Source folder:       {CALIBRATION_VIDEO_FOLDER}\n"
            f"Output TOML:         {calibration_path}\n"
            f"Camera names:        {CALIBRATION_CAMERA_NAMES}\n"
            f"Videos:              {[str(path) for path in videos]}\n"
            f"Board:               {CHARUCO_COLUMNS}x{CHARUCO_ROWS}, "
            f"square={SQUARE_LENGTH}, marker={MARKER_LENGTH}, "
            f"bits={MARKER_BITS}, dictionary={DICTIONARY_SIZE}\n"
            f"Fisheye:             {FISHEYE}\n"
            f"Calibration error:   {error}\n"
            f"Rows returned:       {len(rows) if rows is not None else 'unknown'}\n"
        )

    print_section("CALIBRATION COMPLETED")
    print("Saved calibration:", calibration_path)
    print("Saved log:        ", log_path)
    print("Elapsed time:     ", elapsed)
    print(
        "Reuse this TOML for recordings made while the cameras, lenses, "
        "resolution, and camera order remained unchanged."
    )
    print("[PROGRESS 100%] Calibration finished", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCalibration interrupted by user.")
        raise SystemExit(130)
    except Exception:
        print_section("CALIBRATION FAILED")
        traceback.print_exc()
        print(
            "\nReview the final traceback above. Common causes are a missing "
            "camera video, incorrect camera identifier, wrong board settings, "
            "or an inaccessible network folder."
        )
        raise SystemExit(1)
