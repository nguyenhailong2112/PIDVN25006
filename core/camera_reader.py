import os
import random
import re
import threading
import time

import cv2

from core.frame_store import FrameStore, LiveFrame
from core.logger_config import get_logger
from core.types import IngestConfig


class CameraReader:
    def __init__(
        self,
        camera_id: str,
        source: str,
        frame_store: FrameStore,
        reconnect_delay_sec: float = 2.0,
        expected_fps: float | None = None,
        buffer_size: int = 1,
        ingest_config: IngestConfig | None = None,
    ):
        self.ingest_config = ingest_config or IngestConfig()
        self.camera_id = camera_id
        self.source = self._apply_stream_profile(source, self.ingest_config.stream_profile)
        self.frame_store = frame_store
        self.reconnect_delay_sec = float(self.ingest_config.reconnect_delay_sec if ingest_config is not None else reconnect_delay_sec)
        self.max_reconnect_delay_sec = max(5.0, self.reconnect_delay_sec * 6.0)
        default_expected_fps = self.ingest_config.expected_source_fps
        self.expected_fps = float(expected_fps) if expected_fps and expected_fps > 0 else float(default_expected_fps)
        self.output_fps = max(1.0, float(self.ingest_config.reader_output_fps))
        self.buffer_size = max(1, int(self.ingest_config.buffer_size if ingest_config is not None else buffer_size))
        self.latest_frame_only = bool(self.ingest_config.latest_frame_only)
        self.open_timeout_msec = int(self.ingest_config.open_timeout_msec)
        self.read_timeout_msec = int(self.ingest_config.read_timeout_msec)
        self.skip_sleep_sec = max(0.0, int(self.ingest_config.skip_sleep_ms) / 1000.0)

        self._thread = None
        self._running = False
        self._frame_id = 0
        self._health = "offline"
        self._logger = get_logger(__name__)
        self._reconnect_delay = self.reconnect_delay_sec
        self.reconnect_count = 0

    @staticmethod
    def _apply_stream_profile(source: str, profile: str) -> str:
        if not str(source).lower().startswith("rtsp"):
            return source
        profile_digit = {"main": "1", "sub": "2", "third": "3"}.get(str(profile).lower(), "1")
        return re.sub(r"(/Streaming/Channels/\d+)\d\b", rf"\g<1>{profile_digit}", source)

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
                f"rtsp_transport;{self.ingest_config.rtsp_transport}|fflags;nobuffer|flags;low_delay|max_delay;0|reorder_queue_size;0",
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
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_msec)
            except Exception:
                pass
            try:
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_msec)
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
            publish_interval_sec = 1.0 / max(1.0, self.output_fps)
            last_publish_ts = 0.0

            while self._running:
                if self.latest_frame_only:
                    ret = cap.grab()
                    if not ret:
                        self._health = "offline"
                        self._logger.warning("[%s] Grab failed. Reconnecting...", self.camera_id)
                        break
                    now = time.monotonic()
                    if last_publish_ts and (now - last_publish_ts) < publish_interval_sec:
                        if self.skip_sleep_sec > 0:
                            time.sleep(self.skip_sleep_sec)
                        continue
                    ret, frame = cap.retrieve()
                    last_publish_ts = now
                else:
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
