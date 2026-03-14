import threading
import time
from dataclasses import dataclass


@dataclass
class RunnerStats:
    last_step_ms: float = 0.0
    last_success_ts: float = 0.0


class CameraRunner:
    def __init__(self, processor, target_fps: float = 0.0):
        self.processor = processor
        self.target_fps = max(0.0, float(target_fps))
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._latest_result = None
        self._stats = RunnerStats()

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
        try:
            self.processor.close()
        except Exception:
            pass

    def get_latest(self):
        with self._lock:
            return self._latest_result

    def get_stats(self) -> RunnerStats:
        with self._lock:
            return RunnerStats(
                last_step_ms=self._stats.last_step_ms,
                last_success_ts=self._stats.last_success_ts,
            )

    def _run(self) -> None:
        min_interval = 1.0 / self.target_fps if self.target_fps > 0 else 0.0
        while self._running:
            t0 = time.perf_counter()
            result = self.processor.step()
            elapsed = (time.perf_counter() - t0) * 1000.0

            if result is not None:
                with self._lock:
                    self._latest_result = result
                    self._stats.last_step_ms = elapsed
                    self._stats.last_success_ts = time.time()

            if min_interval > 0:
                dt = time.perf_counter() - t0
                sleep_time = min_interval - dt
                if sleep_time > 0:
                    time.sleep(sleep_time)
