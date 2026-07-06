from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.auto_dispatch_types import ACTIVE_RESERVATION_STATES, make_id, now_text


def _temp_path_for(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp")


def write_json_atomic_local(path: Path, payload: Any, *, indent: int | None = 2) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    separators = None if indent is not None else (",", ":")
    tmp_path = _temp_path_for(path)
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent, separators=separators), encoding="utf-8")
    tmp_path.replace(path)
    return path


def append_jsonl(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


class AutoDispatchLedger:
    """Persistent reservation ledger for Vision-created AMR tasks."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.output_dir / "ledger.json"
        self.events_path = self.output_dir / "events.jsonl"
        self.task_requests_path = self.output_dir / "task_requests.jsonl"
        self.latest_path = self.output_dir / "latest.json"
        self.runtime_state_path = self.output_dir / "runtime_state.json"

    def load(self) -> dict[str, Any]:
        if not self.ledger_path.exists():
            return {"version": 1, "records": []}
        try:
            payload = json.loads(self.ledger_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return {"version": 1, "records": [], "corrupted": True}
        if not isinstance(payload, dict):
            return {"version": 1, "records": [], "corrupted": True}
        payload.setdefault("version", 1)
        payload.setdefault("records", [])
        if not isinstance(payload["records"], list):
            payload["records"] = []
            payload["corrupted"] = True
        return payload

    def save(self, payload: dict[str, Any]) -> None:
        write_json_atomic_local(self.ledger_path, payload)

    def records(self) -> list[dict[str, Any]]:
        return list(self.load().get("records", []))

    def active_records(self) -> list[dict[str, Any]]:
        return [record for record in self.records() if str(record.get("state", "")) in ACTIVE_RESERVATION_STATES]

    def find(self, reservation_id: str) -> dict[str, Any] | None:
        for record in self.records():
            if str(record.get("reservation_id", "")) == reservation_id:
                return record
        return None

    def upsert_record(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = self.load()
        records = payload.setdefault("records", [])
        reservation_id = str(record.get("reservation_id", "")).strip()
        updated = False
        for index, current in enumerate(records):
            if str(current.get("reservation_id", "")) == reservation_id:
                merged = dict(current)
                merged.update(record)
                records[index] = merged
                updated = True
                record = merged
                break
        if not updated:
            records.append(dict(record))
        self.save(payload)
        return dict(record)

    def update_record(self, reservation_id: str, **updates: Any) -> dict[str, Any] | None:
        record = self.find(reservation_id)
        if record is None:
            return None
        record.update(updates)
        record["updated_at"] = float(updates.get("updated_at", time.time()))
        return self.upsert_record(record)

    def create_record(
        self,
        *,
        reservation_id: str,
        mode: str,
        source_position: str,
        dest_position: str,
        source_ref: dict[str, Any],
        dest_ref: dict[str, Any],
        batch_id: str,
        task_code: str,
        req_code: str,
        request_hash: str,
        now_ts: float,
    ) -> dict[str, Any]:
        record = {
            "reservation_id": reservation_id,
            "batch_id": batch_id,
            "req_code": req_code,
            "request_hash": request_hash,
            "task_code": task_code,
            "rcs_task_code": "",
            "mode": mode,
            "source_position": source_position,
            "dest_position": dest_position,
            "source_camera_id": source_ref.get("camera_id", ""),
            "source_zone_id": source_ref.get("zone_id", ""),
            "dest_camera_id": dest_ref.get("camera_id", ""),
            "dest_zone_id": dest_ref.get("zone_id", ""),
            "state": "reserved",
            "created_at": round(now_ts, 3),
            "submitted_at": 0.0,
            "started_at": 0.0,
            "completed_at": 0.0,
            "verified_at": 0.0,
            "updated_at": round(now_ts, 3),
            "last_task_status": "",
            "last_callback_method": "",
            "last_bind_notify_at": 0.0,
            "source_expected_after": "empty",
            "dest_expected_after": "occupied_canonical",
            "dest_canonical_ctnr_code": dest_position,
            "last_error": "",
            "attempt_count": 0,
        }
        self.upsert_record(record)
        self.append_event("reservation_created", record, now_ts=now_ts)
        return record

    def load_runtime_state(self) -> dict[str, Any]:
        if not self.runtime_state_path.exists():
            return {"state": "DISABLED", "mode": "disabled"}
        try:
            payload = json.loads(self.runtime_state_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return {"state": "FAULT", "mode": "disabled", "fault_reason": "runtime_state_corrupted"}
        return payload if isinstance(payload, dict) else {"state": "FAULT", "mode": "disabled"}

    def save_runtime_state(self, payload: dict[str, Any]) -> None:
        write_json_atomic_local(self.runtime_state_path, payload)

    def append_event(self, event_type: str, payload: dict[str, Any], *, now_ts: float | None = None) -> None:
        ts = time.time() if now_ts is None else float(now_ts)
        append_jsonl(
            self.events_path,
            {
                "timestamp": now_text(ts),
                "timestamp_ts": round(ts, 3),
                "event_type": event_type,
                "payload": payload,
            },
        )

    def append_task_request(self, payload: dict[str, Any], response: dict[str, Any], *, now_ts: float | None = None) -> None:
        ts = time.time() if now_ts is None else float(now_ts)
        append_jsonl(
            self.task_requests_path,
            {
                "timestamp": now_text(ts),
                "timestamp_ts": round(ts, 3),
                "request": payload,
                "response": response,
            },
        )

    def write_latest(self, payload: dict[str, Any]) -> None:
        write_json_atomic_local(self.latest_path, payload, indent=None)
