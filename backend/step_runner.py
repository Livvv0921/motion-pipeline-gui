from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

_DLL_DIRECTORY_HANDLES = []


def _prepare_windows_dll_search() -> None:
    """Add the selected Python environment's native-library folders explicitly."""
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return

    prefix = Path(sys.prefix)
    candidates = [
        prefix / "Library" / "bin",
        prefix / "DLLs",
        prefix,
    ]
    # Keep handles alive for the lifetime of this runner.
    global _DLL_DIRECTORY_HANDLES
    _DLL_DIRECTORY_HANDLES = []
    for folder in candidates:
        if folder.is_dir():
            try:
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(folder)))
            except OSError:
                pass


PATH_KEYS = {
    "CONFIG_PATH",
    "VIDEO_ROOT",
    "PROCESS_ROOT",
    "CALIBRATION_VIDEO_FOLDER",
    "CALIBRATION_OUTPUT_ROOT",
    "TRIAL_FOLDER",
    "CALIBRATION_PATH",
    "RAW_VIDEO_ROOT",
    "RAW_VIDEO_FOLDER",
}


def _convert_value(key: str, value):
    if key in PATH_KEYS:
        if value in (None, ""):
            return None
        return Path(value)
    if key == "CAMERA_IDENTIFIERS":
        return [tuple(item) for item in value]
    return value


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("motion_pipeline_backend", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load backend script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one pipeline backend with GUI overrides.")
    parser.add_argument("--script", required=True)
    parser.add_argument("--settings", required=True)
    args = parser.parse_args()

    script_path = Path(args.script).resolve()
    settings_path = Path(args.settings).resolve()

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    _prepare_windows_dll_search()
    print(f"GUI runner Python: {sys.executable}", flush=True)
    print(f"GUI runner sys.prefix: {sys.prefix}", flush=True)
    print(f"GUI runner CONDA_PREFIX: {os.environ.get('CONDA_PREFIX', '(not set)')}", flush=True)
    module = _load_module(script_path)

    print(f"GUI runner loaded: {script_path.name}", flush=True)
    for key, raw_value in settings.items():
        if not hasattr(module, key):
            print(f"GUI NOTE: backend has no setting named {key}; ignoring it.", flush=True)
            continue
        value = _convert_value(key, raw_value)
        setattr(module, key, value)
        print(f"GUI setting: {key} = {value}", flush=True)

    result = module.main()
    if isinstance(result, int):
        return result
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("GUI runner interrupted by user.", flush=True)
        raise SystemExit(130)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
