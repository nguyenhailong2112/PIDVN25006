from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.auto_dispatch_ledger import AutoDispatchLedger, write_json_atomic_local
from core.auto_dispatch_planner import AutoDispatchPlanner
from core.auto_dispatch_types import (
    ACTIVE_RESERVATION_STATES,
    CALLBACK_METHOD_TO_STATE,
    TASK_STATUS_TO_STATE,
    make_id,
    make_task_code,
)
from core.auto_dispatch_site_config import merge_site_call_codes
from core.hik_rcs_task_client import HikRcsTaskClient
from core.logger_config import get_logger
from core.path_utils import PROJECT_ROOT


logger = get_logger(__name__)


class AutoDispatchRuntime:
    """Phase 2 Vision orchestration runtime for AMR pallet tasks."""

    def __init__(
        self,
        auto_config_path: str | Path,
        hik_config_path: str | Path,
        project_root: str | Path = PROJECT_ROOT,
    ) -> None:
        self.project_root = Path(project_root)
        self.auto_config_path = Path(auto_config_path)
        self.hik_config_path = Path(hik_config_path)
        self.output_dir = self.project_root / "outputs" / "runtime" / "auto_dispatch"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.commands_path = self.output_dir / "commands.json"
        self.auto_config = self._load_auto_config()
        self.hik_config = self._load_json(self.hik_config_path, default={})
        self.ledger = AutoDispatchLedger(self.output_dir)
        self.planner = AutoDispatchPlanner(self.auto_config, self.hik_config)
        self.task_client = HikRcsTaskClient(self.hik_config, self.project_root / "outputs" / "runtime")
        self.last_poll_ts_by_task: dict[str, float] = {}

    def reload_config(self) -> None:
        self.auto_config = self._load_auto_config()
        self.hik_config = self._load_json(self.hik_config_path, default={})
        self.planner = AutoDispatchPlanner(self.auto_config, self.hik_config)
        self.task_client = HikRcsTaskClient(self.hik_config, self.project_root / "outputs" / "runtime")

    def update(self, cameras_payload: list[dict[str, Any]] | None = None, now_ts: float | None = None) -> dict[str, Any]:
        now_ts = float(now_ts if now_ts is not None else time.time())
        cameras_payload = cameras_payload if cameras_payload is not None else self.load_latest_cameras_payload()
        self.reload_config()
        bridge_state = self.load_bridge_state()
        runtime_state = self.ledger.load_runtime_state()
        runtime_state = self._apply_command(runtime_state, now_ts)

        enabled = bool(self.auto_config.get("enabled", False))
        mode = str(self.auto_config.get("mode", "disabled")).strip() or "disabled"
        dry_run = bool(self.auto_config.get("dry_run", True))
        manual_active = self._manual_active()

        if not enabled or mode == "disabled":
            runtime_state.update({"state": "DISABLED", "mode": mode, "enabled": enabled})
            self.ledger.save_runtime_state(runtime_state)
            self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
            return runtime_state

        active = self.ledger.active_records()
        max_active = int(self.auto_config.get("max_active_tasks", 1))
        if len(active) > max_active:
            runtime_state.update({"state": "FAULT", "fault_reason": "duplicate_active_reservation"})
            self.ledger.save_runtime_state(runtime_state)
            self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
            return runtime_state

        if active:
            runtime_state.update(self._track_active_record(active[0], cameras_payload, bridge_state, now_ts, dry_run=dry_run))
            self.ledger.save_runtime_state(runtime_state)
            self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
            return runtime_state

        if runtime_state.get("state") in {"PAUSED", "FAULT", "BATCH_DONE"} and mode != "full_auto":
            self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
            return runtime_state

        if mode == "semi_auto":
            if runtime_state.get("state") not in {"BATCH_ARMED", "EVALUATING", "RESERVING", "WAITING_RCS", "VERIFYING_VISION"}:
                runtime_state.update({"state": "IDLE", "mode": mode})
                self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
                return runtime_state
            if int(runtime_state.get("completed_count", 0) or 0) >= int(runtime_state.get("max_tasks", self.auto_config.get("max_tasks_per_batch", 12))):
                runtime_state.update({"state": "BATCH_DONE", "reason": "max_tasks_reached"})
                self.ledger.save_runtime_state(runtime_state)
                self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
                return runtime_state

        if mode == "full_auto":
            if bool(self.auto_config.get("require_manual_interlock", True)) and not self._manual_interlock_configured():
                runtime_state.update({"state": "FAULT", "mode": mode, "fault_reason": "manual_interlock_not_configured"})
                self.ledger.save_runtime_state(runtime_state)
                self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
                return runtime_state
            if manual_active and bool(self.auto_config.get("require_manual_interlock", True)):
                runtime_state.update({"state": "PAUSED_MANUAL", "mode": mode})
                self.ledger.save_runtime_state(runtime_state)
                self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
                return runtime_state
            cooldown_until = float(runtime_state.get("cooldown_until", 0.0) or 0.0)
            if now_ts < cooldown_until:
                runtime_state.update({"state": "AUTO_IDLE", "mode": mode, "cooldown_remaining_sec": round(cooldown_until - now_ts, 3)})
                self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
                return runtime_state

        plan = self.planner.evaluate(
            cameras_payload=cameras_payload,
            bridge_state=bridge_state,
            active_reservations=[],
            now_ts=now_ts,
            mode=mode,
            manual_active=manual_active,
        )
        runtime_state["last_plan"] = plan
        runtime_state["mode"] = mode
        if not plan.get("can_dispatch", False):
            state = str(plan.get("reason", "BLOCKED"))
            runtime_state.update({"state": state, "reason": plan.get("message", state)})
            if mode == "semi_auto" and state in {"BLOCKED_NO_SOURCE", "BLOCKED_NO_DEST"}:
                runtime_state.update({"state": "BATCH_DONE", "reason": state})
            self.ledger.save_runtime_state(runtime_state)
            self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
            return runtime_state

        runtime_state.update(self._reserve_and_submit(plan, runtime_state, now_ts, dry_run=dry_run))
        self.ledger.save_runtime_state(runtime_state)
        self._publish_latest(runtime_state, cameras_payload, bridge_state, now_ts)
        return runtime_state

    def plan_once(self, cameras_payload: list[dict[str, Any]] | None = None, now_ts: float | None = None, mode: str = "semi_auto") -> dict[str, Any]:
        now_ts = float(now_ts if now_ts is not None else time.time())
        self.reload_config()
        return self.planner.evaluate(
            cameras_payload=cameras_payload if cameras_payload is not None else self.load_latest_cameras_payload(),
            bridge_state=self.load_bridge_state(),
            active_reservations=self.ledger.active_records(),
            now_ts=now_ts,
            mode=mode,
            manual_active=self._manual_active(),
        )

    def write_command(self, command: dict[str, Any]) -> None:
        command = dict(command)
        command.setdefault("created_at", round(time.time(), 3))
        write_json_atomic_local(self.commands_path, command)

    def status(self) -> dict[str, Any]:
        return {
            "runtime_state": self.ledger.load_runtime_state(),
            "active_records": self.ledger.active_records(),
            "latest": self._load_json(self.ledger.latest_path, default={}),
        }

    def _apply_command(self, runtime_state: dict[str, Any], now_ts: float) -> dict[str, Any]:
        command = self._load_json(self.commands_path, default={})
        if not command:
            return runtime_state
        command_name = str(command.get("command", "")).strip()
        command_id = str(command.get("command_id", "")).strip() or str(command.get("created_at", ""))
        if command_id and runtime_state.get("last_command_id") == command_id:
            return runtime_state

        if command_name == "start_batch":
            active = self.ledger.active_records()
            if active:
                runtime_state.update({"state": "FAULT", "fault_reason": "start_batch_with_active_reservation"})
            elif runtime_state.get("state") not in {"DISABLED", "IDLE", "BATCH_DONE", "PAUSED", "BLOCKED_NO_SOURCE", "BLOCKED_NO_DEST"}:
                runtime_state.update({"state": "FAULT", "fault_reason": f"start_batch_not_allowed_from_{runtime_state.get('state')}"})
            else:
                runtime_state.update(
                    {
                        "state": "BATCH_ARMED",
                        "mode": "semi_auto",
                        "batch_id": make_id("B", now_ts),
                        "completed_count": 0,
                        "max_tasks": int(command.get("max_tasks", self.auto_config.get("max_tasks_per_batch", 12))),
                        "requested_by": command.get("requested_by", "operator"),
                        "armed_at": round(now_ts, 3),
                    }
                )
        elif command_name == "pause":
            runtime_state.update({"state": "PAUSED", "paused_at": round(now_ts, 3), "pause_reason": command.get("reason", "operator")})
        elif command_name == "resume":
            runtime_state.update({"state": "IDLE", "resumed_at": round(now_ts, 3), "fault_reason": ""})
        elif command_name == "stop":
            runtime_state.update({"state": "BATCH_DONE", "stopped_at": round(now_ts, 3), "reason": command.get("reason", "operator")})
        elif command_name == "clear_fault":
            runtime_state.update({"state": "IDLE", "fault_reason": "", "cleared_at": round(now_ts, 3)})
        runtime_state["last_command_id"] = command_id
        runtime_state["last_command"] = command
        self.ledger.append_event("command_applied", {"command": command, "runtime_state": runtime_state}, now_ts=now_ts)
        self.ledger.save_runtime_state(runtime_state)
        return runtime_state

    def _reserve_and_submit(self, plan: dict[str, Any], runtime_state: dict[str, Any], now_ts: float, *, dry_run: bool) -> dict[str, Any]:
        source = str(plan.get("source", ""))
        dest = str(plan.get("dest", ""))
        mode = str(runtime_state.get("mode", self.auto_config.get("mode", "semi_auto")))
        batch_id = str(runtime_state.get("batch_id", "")) or make_id("B", now_ts)
        task_code = make_task_code(source, dest, now_ts)
        reservation_id = make_id("R", now_ts)
        payload = self.task_client.build_task_payload(
            auto_config=self.auto_config,
            source_position=source,
            dest_position=dest,
            task_code=task_code,
            reservation_id=reservation_id,
            batch_id=batch_id,
            mode=mode,
        )
        payload_errors = self.task_client.validate_task_payload(payload)
        if payload_errors and not dry_run:
            return {"state": "FAULT", "fault_reason": "task_template_not_confirmed", "payload_errors": payload_errors}

        request_hash = self.task_client.payload_hash(payload)
        req_code = self.task_client.make_req_code(f"auto-dispatch:{task_code}:{request_hash}")
        record = self.ledger.create_record(
            reservation_id=reservation_id,
            mode=mode,
            source_position=source,
            dest_position=dest,
            source_ref=plan.get("source_ref", {}),
            dest_ref=plan.get("dest_ref", {}),
            batch_id=batch_id,
            task_code=task_code,
            req_code=req_code,
            request_hash=request_hash,
            now_ts=now_ts,
        )
        response = self.task_client.submit_task(payload=payload, req_code=req_code, dry_run=dry_run)
        self.ledger.append_task_request(payload, response, now_ts=now_ts)

        if str(response.get("code", "")) == "0":
            rcs_task_code = str(response.get("data", "") or task_code)
            self.ledger.update_record(
                str(record.get("reservation_id", "")),
                state="submitted",
                submitted_at=round(now_ts, 3),
                updated_at=round(now_ts, 3),
                rcs_task_code=rcs_task_code,
                attempt_count=int(record.get("attempt_count", 0) or 0) + 1,
            )
            self.ledger.append_event("task_submitted", {"record": record, "response": response}, now_ts=now_ts)
            return {
                "state": "WAITING_RCS",
                "mode": mode,
                "batch_id": batch_id,
                "last_submitted_reservation_id": record.get("reservation_id", ""),
                "last_task_code": task_code,
            }

        failure_state = "submit_unknown" if str(response.get("code", "")).upper() == "HTTP_ERROR" else "operator_recovery_required"
        self.ledger.update_record(
            str(record.get("reservation_id", "")),
            state=failure_state,
            last_error=str(response.get("message", "")),
            updated_at=round(now_ts, 3),
        )
        return {"state": "FAULT", "fault_reason": f"submit_failed:{response.get('message', '')}", "last_response": response}

    def _track_active_record(
        self,
        record: dict[str, Any],
        cameras_payload: list[dict[str, Any]],
        bridge_state: dict[str, Any],
        now_ts: float,
        *,
        dry_run: bool,
    ) -> dict[str, Any]:
        state = str(record.get("state", ""))
        reservation_id = str(record.get("reservation_id", ""))
        task_code = str(record.get("rcs_task_code", "") or record.get("task_code", ""))
        active_watch = self._active_reservation_watch(record, cameras_payload, now_ts)
        if state in {"submitted", "running", "submit_unknown"}:
            callback_state = self._state_from_latest_callback(task_code)
            if callback_state:
                updates: dict[str, Any] = {
                    "state": callback_state["state"],
                    "last_callback_method": callback_state.get("method", ""),
                    "updated_at": round(now_ts, 3),
                }
                if callback_state["state"] == "running" and not record.get("started_at"):
                    updates["started_at"] = round(now_ts, 3)
                if callback_state["state"] == "completed_wait_vision_verify":
                    updates["completed_at"] = round(now_ts, 3)
                self.ledger.update_record(reservation_id, **updates)
                state = callback_state["state"]
            elif self._should_poll(task_code, now_ts):
                query_state = self._state_from_query(task_code, dry_run=dry_run)
                if query_state:
                    updates = {
                        "state": query_state["state"],
                        "last_task_status": query_state.get("task_status", ""),
                        "updated_at": round(now_ts, 3),
                    }
                    if query_state["state"] == "running" and not record.get("started_at"):
                        updates["started_at"] = round(now_ts, 3)
                    if query_state["state"] == "completed_wait_vision_verify":
                        updates["completed_at"] = round(now_ts, 3)
                    self.ledger.update_record(reservation_id, **updates)
                    state = query_state["state"]

            if (
                dry_run
                and bool(self.auto_config.get("dry_run_auto_complete", False))
                and str((self.ledger.find(reservation_id) or record).get("state", "")) in {"submitted", "running"}
            ):
                dry_complete_delay = float(self.auto_config.get("dry_run_complete_after_sec", 0.0))
                submitted_at = float(record.get("submitted_at", 0.0) or now_ts)
                if (now_ts - submitted_at) >= dry_complete_delay:
                    self.ledger.update_record(
                        reservation_id,
                        state="completed_wait_vision_verify",
                        completed_at=round(now_ts, 3),
                        last_task_status="9",
                        updated_at=round(now_ts, 3),
                    )
                    state = "completed_wait_vision_verify"

        latest_record = self.ledger.find(reservation_id) or record
        if str(latest_record.get("state", "")) == "completed_wait_vision_verify":
            completed_at = float(latest_record.get("completed_at", 0.0) or now_ts)
            settle_sec = float(self.auto_config.get("post_task_settle_sec", 3.0))
            if (now_ts - completed_at) < settle_sec:
                return {"state": "VERIFYING_VISION", "mode": latest_record.get("mode", ""), "settle_remaining_sec": round(settle_sec - (now_ts - completed_at), 3)}
            verify = self.planner.verify_record(record=latest_record, cameras_payload=cameras_payload, bridge_state=bridge_state, now_ts=now_ts)
            if verify.get("verified", False):
                self.ledger.update_record(reservation_id, state="verified", verified_at=round(now_ts, 3), updated_at=round(now_ts, 3))
                runtime_state = self.ledger.load_runtime_state()
                completed_count = int(runtime_state.get("completed_count", 0) or 0) + 1
                cooldown = float(self.auto_config.get("dispatch_cooldown_sec", 5.0))
                self.ledger.append_event("reservation_verified", {"reservation_id": reservation_id, "verify": verify}, now_ts=now_ts)
                return {
                    "state": "EVALUATING" if latest_record.get("mode") == "semi_auto" else "AUTO_IDLE",
                    "mode": latest_record.get("mode", ""),
                    "completed_count": completed_count,
                    "cooldown_until": round(now_ts + cooldown, 3),
                }
            timeout_sec = float(self.auto_config.get("post_task_verify_timeout_sec", 30.0))
            if (now_ts - completed_at) >= timeout_sec:
                self.ledger.update_record(
                    reservation_id,
                    state="operator_recovery_required",
                    last_error=str(verify.get("reason", "")),
                    updated_at=round(now_ts, 3),
                )
                return {"state": "FAULT", "fault_reason": f"verification_failed:{verify.get('reason', '')}", "verify": verify}
            return {"state": "VERIFYING_VISION", "verify": verify, "active_watch": active_watch}

        started_at = float(latest_record.get("started_at", 0.0) or latest_record.get("submitted_at", 0.0) or now_ts)
        running_timeout = float(self.auto_config.get("task_running_timeout_sec", 900.0))
        if str(latest_record.get("state", "")) in {"submitted", "running", "submit_unknown"} and (now_ts - started_at) >= running_timeout:
            self.ledger.update_record(reservation_id, state="expired", last_error="task_running_timeout", updated_at=round(now_ts, 3))
            return {"state": "FAULT", "fault_reason": "task_running_timeout"}

        if str(latest_record.get("state", "")) in {"failed", "canceled", "interrupted", "expired", "operator_recovery_required"}:
            return {"state": "FAULT", "fault_reason": str(latest_record.get("last_error", latest_record.get("state", "")))}
        return {
            "state": "WAITING_RCS",
            "active_reservation_id": reservation_id,
            "active_task_code": task_code,
            "active_watch": active_watch,
        }

    def _state_from_latest_callback(self, task_code: str) -> dict[str, Any] | None:
        callback_path = self.project_root / "outputs" / "runtime" / "hik_rcs" / "callbacks" / "agvCallback.jsonl"
        for event in reversed(self._load_jsonl_tail(callback_path, max_items=100)):
            payload = event.get("payload", {}) if isinstance(event, dict) else {}
            if not isinstance(payload, dict):
                continue
            if str(payload.get("taskCode", "")) != task_code:
                continue
            method = str(payload.get("method", "")).strip()
            state = CALLBACK_METHOD_TO_STATE.get(method)
            if state:
                return {"state": state, "method": method}
        return None

    def _state_from_query(self, task_code: str, *, dry_run: bool) -> dict[str, Any] | None:
        req_code = self.task_client.make_req_code(f"queryTaskStatus:{task_code}:{time.time_ns()}")
        dry_run_status = "9" if bool(self.auto_config.get("dry_run_auto_complete", False)) else "2"
        response = self.task_client.query_task_status(
            task_code=task_code,
            req_code=req_code,
            dry_run=dry_run,
            dry_run_status=dry_run_status,
        )
        if str(response.get("code", "")) != "0":
            return None
        data = response.get("data", [])
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return None
        for item in data:
            if not isinstance(item, dict):
                continue
            if str(item.get("taskCode", "")) != task_code:
                continue
            task_status = str(item.get("taskStatus", ""))
            state = TASK_STATUS_TO_STATE.get(task_status)
            if state:
                return {"state": state, "task_status": task_status}
        return None

    def _should_poll(self, task_code: str, now_ts: float) -> bool:
        interval = float(self.auto_config.get("poll_task_status_interval_sec", 3.0))
        last_ts = float(self.last_poll_ts_by_task.get(task_code, 0.0))
        if (now_ts - last_ts) < interval:
            return False
        self.last_poll_ts_by_task[task_code] = now_ts
        return True

    def _manual_active(self) -> bool:
        manual_lock_path = self.auto_config.get("manual_lock_path")
        if not manual_lock_path:
            return False
        path = self._resolve_runtime_path(str(manual_lock_path))
        payload = self._load_json(path, default={})
        return bool(payload.get("active", False)) if isinstance(payload, dict) else False

    def _active_reservation_watch(
        self,
        record: dict[str, Any],
        cameras_payload: list[dict[str, Any]],
        now_ts: float,
    ) -> dict[str, Any]:
        source = str(record.get("source_position", ""))
        dest = str(record.get("dest_position", ""))
        source_state = self._position_state(source, cameras_payload, now_ts)
        dest_state = self._position_state(dest, cameras_payload, now_ts)
        warnings: list[str] = []
        record_state = str(record.get("state", ""))
        if record_state in {"submitted", "running", "submit_unknown"}:
            if dest_state.get("state") == "occupied":
                warnings.append("dest_occupied_before_rcs_complete")
            if not dest_state.get("usable", False):
                warnings.append(f"dest_not_usable:{dest_state.get('reason', 'unknown')}")
            if not source_state.get("usable", False):
                warnings.append(f"source_not_usable:{source_state.get('reason', 'unknown')}")
        return {
            "source": source,
            "dest": dest,
            "source_state": source_state,
            "dest_state": dest_state,
            "warnings": warnings,
        }

    def _position_state(self, position: str, cameras_payload: list[dict[str, Any]], now_ts: float) -> dict[str, Any]:
        positions = self.auto_config.get("positions", {})
        ref = positions.get(position, {}) if isinstance(positions, dict) else {}
        if not isinstance(ref, dict):
            return {"usable": False, "reason": f"{position} missing from positions"}
        camera_id = str(ref.get("camera_id", ""))
        zone_id = str(ref.get("zone_id", ""))
        for camera in cameras_payload:
            if not isinstance(camera, dict) or str(camera.get("camera_id", "")) != camera_id:
                continue
            camera_health = str(camera.get("camera_health", camera.get("health", "unknown")))
            if camera_health != "online":
                return {"usable": False, "reason": f"{camera_id} health={camera_health}", "camera_id": camera_id, "zone_id": zone_id}
            camera_ts = float(camera.get("timestamp", 0.0) or 0.0)
            age_sec = round(now_ts - camera_ts, 3) if camera_ts > 0.0 else None
            for zone in camera.get("zones", []):
                if str(zone.get("zone_id", "")) != zone_id:
                    continue
                return {
                    "usable": str(zone.get("state", "unknown")) in {"occupied", "empty"} and str(zone.get("health", "unknown")) == "online",
                    "state": str(zone.get("state", "unknown")),
                    "health": str(zone.get("health", "unknown")),
                    "score": float(zone.get("score", 0.0) or 0.0),
                    "camera_id": camera_id,
                    "zone_id": zone_id,
                    "age_sec": age_sec,
                }
            return {"usable": False, "reason": f"{camera_id}:{zone_id} missing zone", "camera_id": camera_id, "zone_id": zone_id}
        return {"usable": False, "reason": f"{camera_id} missing snapshot", "camera_id": camera_id, "zone_id": zone_id}

    def _resolve_runtime_path(self, path_text: str) -> Path:
        path = Path(path_text)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _manual_interlock_configured(self) -> bool:
        source = str(self.auto_config.get("manual_interlock_source", "")).strip()
        if not source or source == "TBD_BY_AGV":
            return False
        if source == "operator_command":
            return bool(self.auto_config.get("manual_lock_path"))
        return True

    def load_latest_cameras_payload(self) -> list[dict[str, Any]]:
        process_payload = self._load_json(self.project_root / "outputs" / "runtime" / "process_latest.json", default={})
        if isinstance(process_payload, dict) and isinstance(process_payload.get("cameras"), list):
            return process_payload["cameras"]
        agv_payload = self._load_json(self.project_root / "outputs" / "runtime" / "agv_latest.json", default={})
        if isinstance(agv_payload, dict) and isinstance(agv_payload.get("cameras"), list):
            return agv_payload["cameras"]
        return []

    def load_bridge_state(self) -> dict[str, Any]:
        return self._load_json(self.project_root / "outputs" / "runtime" / "hik_rcs" / "bridge_state.json", default={"zones": {}})

    def _publish_latest(
        self,
        runtime_state: dict[str, Any],
        cameras_payload: list[dict[str, Any]],
        bridge_state: dict[str, Any],
        now_ts: float,
    ) -> None:
        latest = {
            "timestamp": round(now_ts, 3),
            "enabled": bool(self.auto_config.get("enabled", False)),
            "mode": self.auto_config.get("mode", "disabled"),
            "dry_run": bool(self.auto_config.get("dry_run", True)),
            "manual_interlock_active": self._manual_active(),
            "runtime_state": runtime_state,
            "active_records": self.ledger.active_records(),
            "last_plan": runtime_state.get("last_plan", {}),
            "camera_count": len(cameras_payload),
            "bridge_zone_count": len(bridge_state.get("zones", {})) if isinstance(bridge_state, dict) else 0,
        }
        self.ledger.write_latest(latest)

    @staticmethod
    def _load_json(path: str | Path, *, default: Any) -> Any:
        path = Path(path)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return default

    def _load_auto_config(self) -> dict[str, Any]:
        raw = self._load_json(self.auto_config_path, default={})
        return merge_site_call_codes(raw if isinstance(raw, dict) else {}, self.project_root)

    @staticmethod
    def _load_jsonl_tail(path: Path, *, max_items: int) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            return []
        events: list[dict[str, Any]] = []
        for line in lines[-max_items:]:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        return events
