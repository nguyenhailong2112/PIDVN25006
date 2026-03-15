import os
import random
import threading
import time

import cv2

from core.frame_store import FrameStore, LiveFrame
from core.logger_config import get_logger


class CameraReader:
    def __init__(
        self,
        camera_id: str,
        source: str,
        frame_store: FrameStore,
        reconnect_delay_sec: float = 2.0,
        expected_fps: float | None = None,
        buffer_size: int = 1,
    ):
        self.camera_id = camera_id
        self.source = source
        self.frame_store = frame_store
        self.reconnect_delay_sec = reconnect_delay_sec
        self.max_reconnect_delay_sec = max(5.0, float(reconnect_delay_sec) * 6.0)
        self.expected_fps = float(expected_fps) if expected_fps and expected_fps > 0 else 25.0
        self.buffer_size = max(1, int(buffer_size))

        self._thread = None
        self._running = False
        self._frame_id = 0
        self._health = "offline"
        self._logger = get_logger(__name__)
        self._reconnect_delay = float(reconnect_delay_sec)
        self.reconnect_count = 0

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

    def get_health(self) -> str:
        return self._health

    def _open_capture(self):
        if self.source.lower().startswith("rtsp"):
            os.environ.setdefault(
                "OPENCV_FFMPEG_CAPTURE_OPTIONS",
                "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0|reorder_queue_size;0",
            )
        cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        if hasattr(cap, "set"):
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
            except Exception:
                pass
            try:
                cap.set(cv2.CAP_PROP_FPS, self.expected_fps)
            except Exception:
                pass
            try:
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000)
            except Exception:
                pass
            try:
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000)
            except Exception:
                pass
        return cap

    def _run(self) -> None:
        while self._running:
            cap = self._open_capture()
            if not cap.isOpened():
                self._health = "offline"
                self._logger.warning(
                    "[%s] Cannot open source. Retry after %.1fs",
                    self.camera_id,
                    self._reconnect_delay,
                )
                self.reconnect_count += 1
                jitter = random.uniform(0.0, self._reconnect_delay * 0.2)
                time.sleep(self._reconnect_delay + jitter)
                self._reconnect_delay = min(self._reconnect_delay * 2.0, self.max_reconnect_delay_sec)
                continue

            self._logger.info("[%s] Connected to source.", self.camera_id)
            self._health = "online"
            self._reconnect_delay = float(self.reconnect_delay_sec)

            while self._running:
                ret, frame = cap.read()
                if not ret:
                    self._health = "offline"
                    self._logger.warning("[%s] Read failed. Reconnecting...", self.camera_id)
                    break

                self._frame_id += 1
                self.frame_store.update(
                    LiveFrame(
                        camera_id=self.camera_id,
                        frame_id=self._frame_id,
                        timestamp=time.time(),
                        frame=frame,
                    )
                )

            cap.release()
            if self._running:
                self.reconnect_count += 1
                jitter = random.uniform(0.0, self._reconnect_delay * 0.2)
                time.sleep(self._reconnect_delay + jitter)
                self._reconnect_delay = min(self._reconnect_delay * 2.0, self.max_reconnect_delay_sec)
