from __future__ import annotations

import hashlib
import json
import time
from typing import Any


ACTIVE_RESERVATION_STATES = {
    "reserved",
    "submitting",
    "submit_unknown",
    "submitted",
    "running",
    "completed_wait_vision_verify",
}

TERMINAL_RESERVATION_STATES = {
    "verified",
    "failed",
    "canceled",
    "interrupted",
    "expired",
    "operator_recovery_required",
}

TASK_STATUS_TO_STATE = {
    "0": "failed",
    "1": "submitted",
    "2": "running",
    "3": "submitted",
    "4": "canceled",
    "5": "canceled",
    "6": "submitted",
    "9": "completed_wait_vision_verify",
    "10": "interrupted",
}

CALLBACK_METHOD_TO_STATE = {
    "start": "running",
    "outbin": "running",
    "end": "completed_wait_vision_verify",
    "cancel": "canceled",
    "ctu": "canceled",
}


def now_text(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() if ts is None else ts))


def stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def make_id(prefix: str, now_ts: float | None = None) -> str:
    ts = time.time() if now_ts is None else float(now_ts)
    return f"{prefix}{time.strftime('%Y%m%d_%H%M%S', time.localtime(ts))}_{int((ts % 1) * 1000):03d}"


def make_task_code(source: str, dest: str, now_ts: float | None = None) -> str:
    ts = time.time() if now_ts is None else float(now_ts)
    return f"VISION_{source}_TO_{dest}_{time.strftime('%Y%m%d_%H%M%S', time.localtime(ts))}"
