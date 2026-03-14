import time

import cv2
import numpy as np

from core.path_utils import ensure_exists


class ReplaySource:
    def __init__(self, source_path: str, loop: bool = True, target_fps: float | None = None) -> None:
        self.source_path = str(ensure_exists(source_path, "Replay source"))
        self.loop = loop
        self.cap = cv2.VideoCapture(self.source_path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open replay source: {self.source_path}")

        self.frame_id = 0
        self._base_wall = None
        self._base_msec = None
        self._target_fps = float(target_fps) if target_fps and target_fps > 0 else None
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        fallback_fps = float(fps) if fps and fps > 1e-3 else 25.0
        if self._target_fps:
            fallback_fps = self._target_fps
        self._fallback_interval = 1.0 / max(1.0, fallback_fps)

    def _reopen(self) -> bool:
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(self.source_path)
        if not self.cap.isOpened():
            return False
        self.frame_id = 0
        self._base_wall = None
        self._base_msec = None
        return True

    def _read_frame(self) -> tuple[bool, np.ndarray | None]:
        ret, frame = self.cap.read()
        if ret:
            return True, frame
        if not self.loop:
            return False, None
        if not self._reopen():
            return False, None
        return self.cap.read()

    def _get_frame_msec(self) -> float:
        if self._target_fps:
            return float(self.frame_id) * self._fallback_interval * 1000.0
        pos_msec = self.cap.get(cv2.CAP_PROP_POS_MSEC)
        if pos_msec and pos_msec > 1e-3:
            return float(pos_msec)
        return float(self.frame_id) * self._fallback_interval * 1000.0

    def read(self) -> tuple[bool, np.ndarray | None, int, float]:
        ret, frame = self._read_frame()
        if not ret or frame is None:
            return False, None, self.frame_id, time.time()

        self.frame_id += 1
        frame_msec = self._get_frame_msec()
        now = time.time()

        if self._base_wall is None:
            self._base_wall = now
            self._base_msec = frame_msec
        else:
            target_msec = self._base_msec + (now - self._base_wall) * 1000.0
            while frame_msec < target_msec - 5.0:
                ret, frame = self._read_frame()
                if not ret or frame is None:
                    return False, None, self.frame_id, time.time()
                self.frame_id += 1
                frame_msec = self._get_frame_msec()

            ahead_ms = frame_msec - target_msec
            if ahead_ms > 1.0:
                time.sleep(ahead_ms / 1000.0)

        return True, frame, self.frame_id, time.time()

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
