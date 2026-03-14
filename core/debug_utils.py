import time


class StageTimer:
    """Simple timer for measuring detector and pipeline latency."""

    def __init__(self) -> None:
        self.start_time = 0.0

    def start(self) -> None:
        self.start_time = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.start_time) * 1000.0
