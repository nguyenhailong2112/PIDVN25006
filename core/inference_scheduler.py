from __future__ import annotations

import queue
import threading
import time
import atexit
from dataclasses import dataclass
from collections import deque

import torch
from ultralytics import YOLO


@dataclass
class _Request:
    frame: object
    stream_key: str | None
    event: threading.Event
    result: object | None = None

class _SkippedInference:
    pass


_SKIPPED = _SkippedInference()


def is_skipped_result(result: object) -> bool:
    return isinstance(result, _SkippedInference)

class InferenceScheduler:
    def __init__(
        self,
        model: YOLO,
        conf: float,
        imgsz: int | None,
        batch_size: int,
        batch_timeout_ms: int,
        max_pending_requests: int | None = None,
    ) -> None:
        self.model = model
        self.conf = conf
        self.imgsz = imgsz
        self.batch_size = max(1, int(batch_size))
        self.batch_timeout_ms = max(0, int(batch_timeout_ms))

        self.max_pending_requests = max(self.batch_size, int(max_pending_requests or (self.batch_size * 4)))
        self._pending: deque[_Request] = deque()
        self._cv = threading.Condition()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, frame, stream_key: str | None = None) -> object:
        if self._stop_event.is_set():
            raise RuntimeError("InferenceScheduler is stopping")
        req = _Request(frame=frame, stream_key=stream_key, event=threading.Event())
        with self._cv:
            if stream_key is not None:
                for pending_req in list(self._pending):
                    if pending_req.stream_key == stream_key:
                        self._pending.remove(pending_req)
                        pending_req.result = _SKIPPED
                        pending_req.event.set()
                        break

            self._pending.append(req)
            while len(self._pending) > self.max_pending_requests:
                dropped = self._pending.popleft()
                if dropped is req:
                    break
                dropped.result = _SKIPPED
                dropped.event.set()
            self._cv.notify()
        req.event.wait()
        return req.result

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._pending and not self._stop_event.is_set():
                    self._cv.wait()
                if not self._pending and self._stop_event.is_set():
                    break
                first = self._pending.popleft()

            batch = [first]
            start = time.perf_counter()
            timeout_s = self.batch_timeout_ms / 1000.0

            while len(batch) < self.batch_size:
                with self._cv:
                    if self._pending:
                        batch.append(self._pending.popleft())
                        continue
                    remaining = timeout_s - (time.perf_counter() - start)
                    if remaining <= 0:
                        break
                    self._cv.wait(timeout=remaining)
                    if not self._pending:
                        continue
                    batch.append(self._pending.popleft())

            frames = [req.frame for req in batch]
            results = self.model.predict(
                frames,
                conf=self.conf,
                imgsz=self.imgsz,
                verbose=False,
                device=0,
            )

            for req, res in zip(batch, results):
                req.result = res
                req.event.set()

    def close(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        with self._cv:
            self._cv.notify_all()
        self._thread.join(timeout=2.0)


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
        max_pending_requests: int | None = None,
    ) -> InferenceScheduler:
        key = (
            id(model),
            float(conf),
            int(imgsz) if imgsz is not None else None,
            int(batch_size),
            int(batch_timeout_ms),
            int(max_pending_requests or 0),
        )
        with cls._lock:
            scheduler = cls._items.get(key)
            if scheduler is None:
                scheduler = InferenceScheduler(model, conf, imgsz, batch_size, batch_timeout_ms, max_pending_requests)
                cls._items[key] = scheduler
            return scheduler

    @classmethod
    def close_all(cls) -> None:
        with cls._lock:
            items = list(cls._items.values())
            cls._items.clear()
        for scheduler in items:
            scheduler.close()


atexit.register(SchedulerRegistry.close_all)
