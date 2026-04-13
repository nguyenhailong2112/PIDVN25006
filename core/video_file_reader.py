import threading
import time

import cv2

from core.frame_store import FrameStore, LiveFrame
from core.logger_config import get_logger

logger = get_logger(__name__)


class VideoFileReader:
    def __init__(self, camera_id: str, source: str, frame_store: FrameStore, target_fps: float | None = None) -> None:
        self.camera_id = camera_id
        self.source = source
        self.frame_store = frame_store
        self._running = False
        self._thread = None
        self._frame_id = 0
        self._cap = cv2.VideoCapture(self.source)
        self._target_fps = float(target_fps) if target_fps and target_fps > 0 else None
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        fallback_fps = float(fps) if fps and fps > 1e-3 else 25.0
        if self._target_fps:
            fallback_fps = self._target_fps
        self._fallback_interval = 1.0 / max(1.0, fallback_fps)
        self._base_wall = None
        self._base_msec = None
        self._health = "offline"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()

    def get_health(self) -> str:
        return self._health

    def _get_frame_msec(self) -> float:
        if self._target_fps:
            return float(self._frame_id) * self._fallback_interval * 1000.0
        pos_msec = self._cap.get(cv2.CAP_PROP_POS_MSEC)
        if pos_msec and pos_msec > 1e-3:
            return float(pos_msec)
        return float(self._frame_id) * self._fallback_interval * 1000.0

    def _reset_to_start(self) -> None:
        try:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._health = "online"
        except Exception:
            logger.exception("Failed to reset video reader for %s", self.camera_id)
            self._health = "offline"
        self._frame_id = 0
        self._base_wall = None
        self._base_msec = None

    def _run(self) -> None:
        self._health = "online"
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                self._reset_to_start()
                continue

            self._frame_id += 1
            frame_msec = self._get_frame_msec()
            now = time.time()

            if self._base_wall is None:
                self._base_wall = now
                self._base_msec = frame_msec
            else:
                target_msec = self._base_msec + (now - self._base_wall) * 1000.0
                while frame_msec < target_msec - 5.0:
                    ret, frame = self._cap.read()
                    if not ret:
                        self._reset_to_start()
                        break
                    self._frame_id += 1
                    frame_msec = self._get_frame_msec()

                if not ret:
                    continue

                ahead_ms = frame_msec - target_msec
                if ahead_ms > 1.0:
                    time.sleep(ahead_ms / 1000.0)

            self.frame_store.update(
                LiveFrame(
                    camera_id=self.camera_id,
                    frame_id=self._frame_id,
                    timestamp=time.time(),
                    frame=frame,
                )
            )