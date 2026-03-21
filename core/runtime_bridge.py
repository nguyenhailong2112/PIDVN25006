from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from core.path_utils import PROJECT_ROOT

RUNTIME_DIR = PROJECT_ROOT / "outputs" / "runtime"
SELECTED_CAMERAS_PATH = RUNTIME_DIR / "selected_cameras.json"
PROCESS_SNAPSHOT_PATH = RUNTIME_DIR / "process_latest.json"
AGV_SNAPSHOT_PATH = RUNTIME_DIR / "agv_latest.json"
PROCESS_CAMERA_DIR = RUNTIME_DIR / "cameras"
PROCESS_DEBUG_DIR = RUNTIME_DIR / "debug"
PROCESS_PREVIEW_DIR = RUNTIME_DIR / "preview"


def ensure_runtime_dirs() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    PROCESS_CAMERA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESS_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    PROCESS_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def load_selected_cameras() -> set[str]:
    ensure_runtime_dirs()
    if not SELECTED_CAMERAS_PATH.exists():
        return set()
    try:
        payload = json.loads(SELECTED_CAMERAS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    cameras = payload.get("camera_ids", []) if isinstance(payload, dict) else []
    return {str(camera_id) for camera_id in cameras}


def save_selected_cameras(camera_ids: Iterable[str]) -> Path:
    ensure_runtime_dirs()
    ordered = sorted({str(camera_id) for camera_id in camera_ids})
    SELECTED_CAMERAS_PATH.write_text(
        json.dumps({"camera_ids": ordered}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return SELECTED_CAMERAS_PATH


def camera_snapshot_path(camera_id: str) -> Path:
    ensure_runtime_dirs()
    return PROCESS_CAMERA_DIR / f"{camera_id}.json"


def camera_debug_path(camera_id: str) -> Path:
    ensure_runtime_dirs()
    return PROCESS_DEBUG_DIR / f"{camera_id}.jpg"


def camera_preview_path(camera_id: str) -> Path:
    ensure_runtime_dirs()
    return PROCESS_PREVIEW_DIR / f"{camera_id}.jpg"