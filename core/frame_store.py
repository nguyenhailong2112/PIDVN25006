import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class LiveFrame:
    camera_id: str
    frame_id: int
    timestamp: float
    frame: np.ndarray


class FrameStore:
    def __init__(self) -> None:
        self._frames: dict[str, LiveFrame] = {}
        self._lock = threading.Lock()

    def update(self, live_frame: LiveFrame) -> None:
        with self._lock:
            self._frames[live_frame.camera_id] = live_frame

    def get_latest(self, camera_id: str) -> Optional[LiveFrame]:
        with self._lock:
            return self._frames.get(camera_id)
