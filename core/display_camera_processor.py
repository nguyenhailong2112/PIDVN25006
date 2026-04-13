from pathlib import Path
import time

import cv2

from core.camera_reader import CameraReader
from core.frame_store import FrameStore
from core.path_utils import ensure_exists, resolve_project_path


class _VideoLoopSource:
    def __init__(self, source_path: str) -> None:
        self.source_path = str(ensure_exists(source_path, "Video source"))
        self.cap = cv2.VideoCapture(self.source_path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open video source: {self.source_path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 0.0

    def read(self):
        ret, frame = self.cap.read()
        if ret:
            return True, frame

        self.cap.release()
        self.cap = cv2.VideoCapture(self.source_path)
        if not self.cap.isOpened():
            return False, None
        ret, frame = self.cap.read()
        return ret, frame

    def release(self):
        if self.cap is not None:
            self.cap.release()


class DisplayCameraProcessor:
    def __init__(self, project_root, camera_config) -> None:
        self.project_root = Path(project_root)
        self.camera_config = camera_config
        self.frame_id = 0
        self._last_ts = time.time()
        self.suggested_fps = 0.0

        if camera_config.source_type in {"rtsp", "live"}:
            self.frame_store = FrameStore()
            self.reader = CameraReader(camera_config.camera_id, camera_config.source_path, self.frame_store)
            self.reader.start()
            self.source = None
        else:
            source_path = resolve_project_path(camera_config.source_path)
            self.source = _VideoLoopSource(str(source_path))
            self.suggested_fps = float(self.source.fps or 0.0)
            self.reader = None
            self.frame_store = None

    def step(self):
        if self.reader is not None:
            live_frame = self.frame_store.get_latest(self.camera_config.camera_id)
            if live_frame is None:
                return None
            frame = live_frame.frame
            ts = live_frame.timestamp
        else:
            ok, frame = self.source.read()
            if not ok or frame is None:
                return None
            ts = time.time()

        self.frame_id += 1
        self._last_ts = ts

        return {
            "camera_id": self.camera_config.camera_id,
            "camera_name": self.camera_config.name,
            "timestamp": ts,
            "frame_id": self.frame_id,
            "raw_frame": frame,
        }

    def close(self) -> None:
        if self.reader is not None:
            self.reader.stop()
        if self.source is not None:
            self.source.release()
