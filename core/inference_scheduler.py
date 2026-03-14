from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

from ultralytics import YOLO


@dataclass
class _Request:
    frame: object
    event: threading.Event
    result: object | None = None


class InferenceScheduler:
    def __init__(
        self,
        model: YOLO,
        conf: float,
        imgsz: int | None,
        batch_size: int,
        batch_timeout_ms: int,
    ) -> None:
        self.model = model
        self.conf = conf
        self.imgsz = imgsz
        self.batch_size = max(1, int(batch_size))
        self.batch_timeout_ms = max(0, int(batch_timeout_ms))

        self._queue: queue.Queue[_Request] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, frame) -> object:
        req = _Request(frame=frame, event=threading.Event())
        self._queue.put(req)
        req.event.wait()
        return req.result

    def _run(self) -> None:
        while True:
            first = self._queue.get()
            if first is None:
                continue

            batch = [first]
            start = time.perf_counter()
            timeout_s = self.batch_timeout_ms / 1000.0

            while len(batch) < self.batch_size:
                remaining = timeout_s - (time.perf_counter() - start)
                if remaining <= 0:
                    break
                try:
                    req = self._queue.get(timeout=remaining)
                except queue.Empty:
                    break
                batch.append(req)

            frames = [req.frame for req in batch]
            results = self.model.predict(
                frames,
                conf=self.conf,
                imgsz=self.imgsz,
                verbose=False,
            )

            for req, res in zip(batch, results):
                req.result = res
                req.event.set()


class SchedulerRegistry:
    _lock = threading.Lock()
    _items: dict[tuple, InferenceScheduler] = {}

    @classmethod
    def get(
        cls,
        model: YOLO,
        conf: float,
        imgsz: int | None,
        batch_size: int,
        batch_timeout_ms: int,
    ) -> InferenceScheduler:
        key = (
            id(model),
            float(conf),
            int(imgsz) if imgsz is not None else None,
            int(batch_size),
            int(batch_timeout_ms),
        )
        with cls._lock:
            scheduler = cls._items.get(key)
            if scheduler is None:
                scheduler = InferenceScheduler(model, conf, imgsz, batch_size, batch_timeout_ms)
                cls._items[key] = scheduler
            return scheduler
