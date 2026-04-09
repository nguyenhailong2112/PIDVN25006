from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SCRIPT = PROJECT_ROOT / "mainProcess.py"
FRONTEND_SCRIPT = PROJECT_ROOT / "mainCCTV.py"
SUPERVISOR_DIR = PROJECT_ROOT / "outputs" / "runtime" / "supervisor"
SUPERVISOR_LOG_PATH = SUPERVISOR_DIR / "supervisor.log"


def setup_logger() -> logging.Logger:
    SUPERVISOR_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pidvn25006.supervisor")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = TimedRotatingFileHandler(
        SUPERVISOR_LOG_PATH,
        when="D",
        interval=1,
        backupCount=10,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


LOGGER = setup_logger()


@dataclass
class ManagedProcess:
    name: str
    script_path: Path
    enabled: bool = True
    process: subprocess.Popen | None = None
    restart_count: int = 0
    last_start_ts: float = 0.0

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is not None:
            self.process = None
            return
        LOGGER.info("Stopping %s (pid=%s)", self.name, self.process.pid)
        try:
            self.process.terminate()
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            LOGGER.warning("%s did not exit after terminate(), forcing kill", self.name)
            self.process.kill()
            self.process.wait(timeout=5)
        finally:
            self.process = None


class RuntimeSupervisor:
    def __init__(
        self,
        *,
        python_executable: str,
        start_frontend: bool,
        initial_frontend_delay_sec: float,
        restart_delay_sec: float,
        crash_backoff_sec: float,
        poll_interval_sec: float,
    ) -> None:
        self.python_executable = python_executable
        self.initial_frontend_delay_sec = max(0.0, float(initial_frontend_delay_sec))
        self.restart_delay_sec = max(0.0, float(restart_delay_sec))
        self.crash_backoff_sec = max(self.restart_delay_sec, float(crash_backoff_sec))
        self.poll_interval_sec = max(0.2, float(poll_interval_sec))
        self.stop_requested = False
        self.start_frontend = self._should_start_frontend(start_frontend)

        self.backend = ManagedProcess(name="backend", script_path=BACKEND_SCRIPT, enabled=True)
        self.frontend = ManagedProcess(name="frontend", script_path=FRONTEND_SCRIPT, enabled=self.start_frontend)
        self.processes = [self.backend, self.frontend]

    @staticmethod
    def _should_start_frontend(requested: bool) -> bool:
        if not requested:
            return False
        if sys.platform.startswith("linux"):
            display = os.environ.get("DISPLAY", "").strip()
            wayland_display = os.environ.get("WAYLAND_DISPLAY", "").strip()
            if not display and not wayland_display:
                LOGGER.warning(
                    "Frontend requested but no DISPLAY/WAYLAND_DISPLAY detected. "
                    "Supervisor will run backend only."
                )
                return False
        return True

    def request_stop(self, *_args) -> None:
        if self.stop_requested:
            return
        self.stop_requested = True
        LOGGER.info("Stop requested. Supervisor will terminate child processes.")

    def run(self) -> int:
        signal.signal(signal.SIGINT, self.request_stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, self.request_stop)

        try:
            self._start_process(self.backend, delay_sec=0.0)
            if self.frontend.enabled:
                self._start_process(self.frontend, delay_sec=self.initial_frontend_delay_sec)

            while not self.stop_requested:
                for managed in self.processes:
                    if not managed.enabled:
                        continue
                    self._ensure_running(managed)
                time.sleep(self.poll_interval_sec)
        finally:
            for managed in reversed(self.processes):
                managed.stop()
            LOGGER.info("Supervisor stopped cleanly.")
        return 0

    def _ensure_running(self, managed: ManagedProcess) -> None:
        if managed.process is None:
            self._start_process(managed, delay_sec=self.restart_delay_sec)
            return
        exit_code = managed.process.poll()
        if exit_code is None:
            return

        runtime_sec = time.time() - managed.last_start_ts
        LOGGER.error(
            "%s exited with code=%s after %.1f sec. Restart count=%s",
            managed.name,
            exit_code,
            runtime_sec,
            managed.restart_count,
        )
        managed.process = None

        delay_sec = self.restart_delay_sec
        if runtime_sec < 15.0:
            delay_sec = self.crash_backoff_sec
            LOGGER.warning(
                "%s exited too quickly. Applying crash backoff %.1f sec",
                managed.name,
                delay_sec,
            )
        self._start_process(managed, delay_sec=delay_sec)

    def _start_process(self, managed: ManagedProcess, delay_sec: float) -> None:
        if self.stop_requested or not managed.enabled:
            return
        if delay_sec > 0:
            LOGGER.info("Waiting %.1f sec before starting %s", delay_sec, managed.name)
            time.sleep(delay_sec)
            if self.stop_requested:
                return

        command = [self.python_executable, str(managed.script_path)]
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        LOGGER.info("Starting %s with command=%s", managed.name, command)
        managed.process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            creationflags=creationflags,
        )
        managed.restart_count += 1
        managed.last_start_ts = time.time()
        LOGGER.info("%s started with pid=%s", managed.name, managed.process.pid)


def resolve_python_executable(cli_value: str | None) -> str:
    if cli_value:
        return cli_value
    return sys.executable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PIDVN25006 backend/frontend forever with auto-restart.")
    parser.add_argument("--python", default="", help="Python executable to use for child processes.")
    parser.add_argument("--no-frontend", action="store_true", help="Only supervise backend `mainProcess.py`.")
    parser.add_argument("--frontend-delay-sec", type=float, default=3.0, help="Delay before starting frontend.")
    parser.add_argument("--restart-delay-sec", type=float, default=3.0, help="Normal restart delay after exit.")
    parser.add_argument("--crash-backoff-sec", type=float, default=10.0, help="Restart delay for fast crash loops.")
    parser.add_argument("--poll-interval-sec", type=float, default=1.0, help="Supervisor polling interval.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    supervisor = RuntimeSupervisor(
        python_executable=resolve_python_executable(args.python or None),
        start_frontend=not args.no_frontend,
        initial_frontend_delay_sec=args.frontend_delay_sec,
        restart_delay_sec=args.restart_delay_sec,
        crash_backoff_sec=args.crash_backoff_sec,
        poll_interval_sec=args.poll_interval_sec,
    )
    return supervisor.run()


if __name__ == "__main__":
    raise SystemExit(main())
