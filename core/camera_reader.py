import os
import threading
import time

import cv2

from core.frame_store import FrameStore, LiveFrame


class CameraReader:
    def __init__(self, camera_id: str, source: str, frame_store: FrameStore, reconnect_delay_sec: float = 2.0):
        self.camera_id = camera_id
        self.source = source
        self.frame_store = frame_store
        self.reconnect_delay_sec = reconnect_delay_sec

        self._thread = None
        self._running = False
        self._frame_id = 0
        self._health = "offline"
        self._max_drain = 3

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
                "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0",
            )
        cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        if hasattr(cap, "set"):
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            try:
                cap.set(cv2.CAP_PROP_FPS, 25)
            except Exception:
                pass
        return cap

    def _run(self) -> None:
        while self._running:
            cap = self._open_capture()
            if not cap.isOpened():
                self._health = "offline"
                print(f"[{self.camera_id}] Cannot open source. Retry after {self.reconnect_delay_sec}s")
                time.sleep(self.reconnect_delay_sec)
                continue

            print(f"[{self.camera_id}] Connected to source.")
            self._health = "online"

            while self._running:
                if not cap.grab():
                    self._health = "offline"
                    print(f"[{self.camera_id}] Read failed. Reconnecting...")
                    break

                for _ in range(self._max_drain):
                    if not cap.grab():
                        break

                ret, frame = cap.retrieve()
                if not ret:
                    self._health = "offline"
                    print(f"[{self.camera_id}] Retrieve failed. Reconnecting...")
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
                time.sleep(self.reconnect_delay_sec)
