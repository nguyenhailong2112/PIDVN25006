from __future__ import annotations

import json
from pathlib import Path

from core.file_utils import write_text_atomic
from core.logger_config import get_logger


logger = get_logger(__name__)


class RuntimeMaintenance:
    def __init__(self, project_root: Path, runtime_cfg: dict) -> None:
        self.project_root = Path(project_root)
        self.enabled = bool(runtime_cfg.get("log_cleanup_enabled", True))
        self.interval_sec = max(300.0, float(runtime_cfg.get("log_cleanup_interval_sec", 3600.0)))
        self.retention_sec = max(self.interval_sec, float(runtime_cfg.get("log_retention_hours", 24.0)) * 3600.0)
        self.last_run_ts = 0.0

        outputs_dir = self.project_root / "outputs"
        self.history_dir = outputs_dir / "history"
        self.hik_dir = outputs_dir / "runtime" / "hik_rcs"
        self.supervisor_dir = outputs_dir / "runtime" / "supervisor"

    def run_if_due(self, now_ts: float) -> None:
        if not self.enabled:
            return
        if self.last_run_ts and (now_ts - self.last_run_ts) < self.interval_sec:
            return
        self.last_run_ts = now_ts
        cutoff_ts = now_ts - self.retention_sec

        try:
            self._prune_history_logs(cutoff_ts)
            self._delete_old_rotated_files(self.history_dir, "*.jsonl.*", cutoff_ts)
            self._delete_old_rotated_files(self.hik_dir, "*.jsonl.*", cutoff_ts)
            self._delete_old_rotated_files(self.supervisor_dir, "*.log.*", cutoff_ts)
            self._delete_stale_files(self.hik_dir, "*.jsonl", cutoff_ts)
            self._delete_stale_files(self.supervisor_dir, "*.log", cutoff_ts)
        except Exception:
            logger.exception("RuntimeMaintenance cleanup failed")

    def _prune_history_logs(self, cutoff_ts: float) -> None:
        if not self.history_dir.exists():
            return
        for path in self.history_dir.glob("*.jsonl"):
            self._prune_jsonl_file(path, cutoff_ts)

    def _prune_jsonl_file(self, path: Path, cutoff_ts: float) -> None:
        try:
            original_lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return
        except Exception:
            logger.exception("Failed to read history log for pruning: %s", path)
            return

        kept_lines: list[str] = []
        removed_count = 0
        for line in original_lines:
            if not line.strip():
                continue
            keep_line = True
            try:
                payload = json.loads(line)
                timestamp_value = payload.get("timestamp")
                if isinstance(timestamp_value, (int, float)) and float(timestamp_value) < cutoff_ts:
                    keep_line = False
            except Exception:
                keep_line = True
            if keep_line:
                kept_lines.append(line)
            else:
                removed_count += 1

        if removed_count <= 0:
            return

        if kept_lines:
            write_text_atomic(path, "\n".join(kept_lines) + "\n")
        else:
            path.unlink(missing_ok=True)
        logger.info("[MAINTENANCE] pruned %d old history lines from %s", removed_count, path)

    @staticmethod
    def _delete_old_rotated_files(root_dir: Path, pattern: str, cutoff_ts: float) -> None:
        if not root_dir.exists():
            return
        for path in root_dir.rglob(pattern):
            RuntimeMaintenance._delete_file_if_older(path, cutoff_ts)

    @staticmethod
    def _delete_stale_files(root_dir: Path, pattern: str, cutoff_ts: float) -> None:
        if not root_dir.exists():
            return
        for path in root_dir.rglob(pattern):
            if any(suffix.isdigit() for suffix in path.suffixes):
                continue
            RuntimeMaintenance._delete_file_if_older(path, cutoff_ts)

    @staticmethod
    def _delete_file_if_older(path: Path, cutoff_ts: float) -> None:
        try:
            modified_ts = path.stat().st_mtime
        except FileNotFoundError:
            return
        if modified_ts >= cutoff_ts:
            return
        try:
            path.unlink()
            logger.info("[MAINTENANCE] deleted stale file %s", path)
        except FileNotFoundError:
            return
        except OSError:
            logger.exception("Failed to delete stale file: %s", path)
