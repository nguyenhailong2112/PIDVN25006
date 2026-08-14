from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from ipaddress import ip_address

from core.file_utils import append_jsonl_rotating, write_json_atomic
from core.hik_rcs_client import HikRcsClient
from core.logger_config import get_logger


logger = get_logger(__name__)


class AutoDispatcher:
    """Runs one independently controlled Vision-to-RCS dispatch lane."""

    ALLOWED_PROFILES = {"PK_AB", "PK_CD"}

    def __init__(self, config: dict[str, Any], hik_config: dict[str, Any], project_root: str | Path) -> None:
        self.config = config or {}
        self.project_root = Path(project_root)
        self.dispatcher_id = str(self.config.get("dispatcher_id", "amr")).strip().lower() or "amr"
        runtime_dir = str(self.config.get("runtime_dir", "outputs/runtime/auto_dispatch")).strip()
        self.output_dir = self.project_root / runtime_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.output_dir / "state.json"
        self.event_log_path = self.output_dir / "events.jsonl"
        self.control_event_log_path = self.output_dir / "control_api.jsonl"
        self.control_latest_path = self.output_dir / "control_api_latest.json"
        self.enabled = bool(self.config.get("enabled", False))
        self.dry_run = bool(self.config.get("dry_run", True))
        self.require_bind_notify = bool(self.config.get("require_bind_notify", True))
        self.require_canonical = bool(self.config.get("require_canonical", True))
        self.callback_server_enabled = bool(hik_config.get("callback_server", {}).get("enabled", False))
        self.query_interval_sec = max(1.0, float(self.config.get("query_interval_sec", 5.0)))
        self.completed_statuses = {
            str(item).strip().lower()
            for item in self.config.get("completed_statuses", ["completed", "complete", "finish", "finished", "ended", "success"])
            if str(item).strip()
        }
        self.failed_statuses = {
            str(item).strip().lower()
            for item in self.config.get("failed_statuses", ["failed", "fail", "cancel", "canceled", "cancelled", "abort", "aborted"])
            if str(item).strip()
        }
        self.query_status_agv_code = str(self.config.get("query_status_agv_code", "")).strip()
        configured_profiles = self.config.get("dispatch_profiles", {})
        self.allowed_profiles = {
            str(profile_id).strip()
            for profile_id in configured_profiles
            if str(profile_id).strip()
        } or set(self.ALLOWED_PROFILES)
        self.client = HikRcsClient(hik_config, self.project_root / "outputs" / "runtime" / "hik_rcs")
        self.state = self._load_state()
        self.api_server = None
        api_cfg = self.config.get("api_server", {})
        if isinstance(api_cfg, dict) and api_cfg.get("enabled", False):
            self.api_server = AutoDispatchControlServer(api_cfg, self)
            self.api_server.start()

    def close(self) -> None:
        self._save_state()
        if self.api_server is not None:
            self.api_server.stop()

    def sync(self, cameras_payload: list[dict[str, Any]], bridge_state: dict[str, Any], now_ts: float | None = None) -> None:
        now_ts = float(now_ts if now_ts is not None else time.time())
        if not self.enabled:
            return

        control = self._load_control()
        if str(control.get("operation_mode", self.config.get("operation_mode", "manual"))).strip().lower() != "auto":
            self._set_idle("manual_mode", now_ts)
            return
        if self.require_bind_notify and not self.callback_server_enabled:
            self._set_idle("bind_notify_callback_disabled", now_ts)
            return

        profile_id = str(control.get("profile_id", self.config.get("profile_id", ""))).strip()
        if profile_id not in self.allowed_profiles:
            self._set_idle(f"unsupported_profile:{profile_id}", now_ts)
            return

        if self._refresh_active_task(now_ts):
            self._save_state()
            return

        position_states = self._collect_position_states(cameras_payload)
        profile = dict(self.config.get("dispatch_profiles", {}).get(profile_id, {}))
        source_order = [str(item) for item in profile.get("source_order", [])]
        required_occupied_count = int(profile.get("required_occupied_count", len(source_order)))
        if not source_order or required_occupied_count <= 0:
            self._set_idle(f"invalid_profile:{profile_id}", now_ts)
            return

        batch = self.state.get("batch") if isinstance(self.state.get("batch"), dict) else None
        if not batch or batch.get("profile_id") != profile_id:
            occupied_sources = [position for position in source_order if self._position_state(position_states, position) == "occupied"]
            if len(occupied_sources) != required_occupied_count:
                self._set_idle(f"waiting_pk_full:{profile_id}:{len(occupied_sources)}/{required_occupied_count}", now_ts)
                return
            batch = {
                "profile_id": profile_id,
                "source_order": source_order,
                "dispatched_sources": [],
                "dispatched_dests": [],
                "created_at": round(now_ts, 3),
            }
            self.state["batch"] = batch
            self._log_event("batch_started", {"profile_id": profile_id, "source_order": source_order}, now_ts)

        destination_empty = self._empty_destination_positions(position_states, batch)
        minimum_empty = int(profile.get("minimum_empty_destination_slots", profile.get("minimum_empty_fg_slots", 1)) or 1)
        if len(destination_empty) < minimum_empty:
            self._log_event("batch_stopped_no_destination_empty", {"profile_id": profile_id, "batch": batch}, now_ts)
            self.state.pop("batch", None)
            self._set_status("stopped_no_destination_empty", now_ts)
            self._save_state()
            return

        source = self._next_source(batch, position_states)
        if not source:
            if self._all_sources_dispatched(batch):
                self._log_event("batch_completed", {"profile_id": profile_id}, now_ts)
                self._set_status("batch_completed", now_ts)
            else:
                self._log_event("batch_stopped_source_not_occupied", {"profile_id": profile_id, "batch": batch}, now_ts)
                self._set_status("stopped_source_not_occupied", now_ts)
            self.state.pop("batch", None)
            self._save_state()
            return

        dest = destination_empty[0]
        guard_ok, guard_reason = self._bind_guard_ok(source, "occupied", bridge_state)
        if guard_ok:
            guard_ok, guard_reason = self._bind_guard_ok(dest, "empty", bridge_state)
        if not guard_ok:
            self._set_status(f"blocked_bind_guard:{guard_reason}", now_ts)
            self._save_state()
            return

        self._create_task(profile_id=profile_id, source=source, dest=dest, batch=batch, now_ts=now_ts)
        self._save_state()

    def _create_task(self, *, profile_id: str, source: str, dest: str, batch: dict[str, Any], now_ts: float) -> None:
        source_call_code = self._source_call_code(source)
        dest_call_code = str(self.config.get("routing", {}).get("destination_area", {}).get("call_code", "")).strip()
        if not source_call_code or not dest_call_code:
            self._set_status("blocked_missing_call_code", now_ts)
            return

        task_template = self.config.get("task_template", {})
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now_ts))
        compact_source = source.replace("_", "")
        compact_dest = dest.replace("_", "")
        compact_stamp = stamp.replace("_", "")
        task_prefix = str(task_template.get("task_code_prefix", task_template.get("taskTyp", "QUANGPRO"))).strip()
        task_code = f"{task_prefix}{compact_source}{compact_dest}{compact_stamp}"
        static_fields = task_template.get("static_fields", {})
        payload = dict(static_fields) if isinstance(static_fields, dict) else {}
        payload.update(
            {
                "interfaceName": str(task_template.get("interfaceName", "genAgvSchedulingTask")),
                "taskTyp": str(task_template.get("taskTyp", "QUANGPRO")),
                str(task_template.get("path_field", "userCallCodePath")): [source_call_code, dest_call_code],
                "ctnrTyp": str(task_template.get("ctnrTyp", "2")),
            }
        )
        if bool(task_template.get("send_task_code", True)):
            payload["taskCode"] = task_code
        if bool(task_template.get("include_data", True)):
            payload["data"] = {
                "from": source,
                "to": dest,
            }
        req_code = self.client.make_req_code(task_code)
        if self.dry_run:
            response = {"code": "0", "message": "dry_run", "reqCode": req_code, "data": ""}
            logger.info("[AUTO-DISPATCH] dry_run task=%s payload=%s", task_code, payload)
        else:
            response = self.client.call_rpc(str(task_template.get("api", "genAgvSchedulingTask")), payload, req_code=req_code)

        active_task = {
            "profile_id": profile_id,
            "task_code": task_code,
            "source": source,
            "dest": dest,
            "payload": payload,
            "req_code": req_code,
            "response": response,
            "created_at": round(now_ts, 3),
            "last_query_at": 0.0,
            "status": "created" if self.client.is_success(response) else "create_failed",
        }
        if self.client.is_success(response):
            dispatched = list(batch.get("dispatched_sources", []))
            if source not in dispatched:
                dispatched.append(source)
            batch["dispatched_sources"] = dispatched
            dispatched_dests = list(batch.get("dispatched_dests", []))
            if dest not in dispatched_dests:
                dispatched_dests.append(dest)
            batch["dispatched_dests"] = dispatched_dests
            self.state["active_task"] = active_task
            self._set_status(f"task_created:{task_code}", now_ts)
            self._log_event("task_created", active_task, now_ts)
        else:
            self.state["last_failed_task"] = active_task
            self._set_status(f"task_create_failed:{task_code}", now_ts)
            self._log_event("task_create_failed", active_task, now_ts)

    def _refresh_active_task(self, now_ts: float) -> bool:
        active = self.state.get("active_task")
        if not isinstance(active, dict):
            return False
        task_code = str(active.get("task_code", "")).strip()
        if not task_code:
            self.state.pop("active_task", None)
            return False

        if self.dry_run:
            active["status"] = "completed"
            active["completed_at"] = round(now_ts, 3)
            self.state["last_completed_task"] = active
            self.state.pop("active_task", None)
            self._log_event("task_completed", active, now_ts)
            return True

        last_query_at = float(active.get("last_query_at", 0.0) or 0.0)
        if now_ts - last_query_at < self.query_interval_sec:
            self._set_status(f"waiting_task:{task_code}", now_ts)
            return True

        query_payload = {"taskCodes": [task_code]}
        if self.query_status_agv_code:
            query_payload["agvCode"] = self.query_status_agv_code
        response = self.client.call_rpc("queryTaskStatus", query_payload)
        active["last_query_at"] = round(now_ts, 3)
        own_response = self._extract_own_task_response(response, task_code)
        active["last_query_response"] = own_response
        task_status = self._extract_task_status(own_response)
        active["status"] = task_status or str(response.get("message", "")).strip() or str(response.get("code", ""))
        normalized = active["status"].strip().lower()
        if self.client.is_success(response) and normalized in self.completed_statuses:
            active["completed_at"] = round(now_ts, 3)
            self.state["last_completed_task"] = active
            self.state.pop("active_task", None)
            self._log_event("task_completed", active, now_ts)
            return True
        if normalized in self.failed_statuses:
            active["failed_at"] = round(now_ts, 3)
            self.state["last_failed_task"] = active
            self.state.pop("active_task", None)
            self._log_event("task_failed", active, now_ts)
            return True
        self._set_status(f"waiting_task:{task_code}:{active['status']}", now_ts)
        return True

    def _bind_guard_ok(self, position: str, required_state: str, bridge_state: dict[str, Any]) -> tuple[bool, str]:
        pos_cfg = self.config.get("positions", {}).get(position, {})
        key = f"{pos_cfg.get('camera_id', '')}:{pos_cfg.get('zone_id', '')}:bindCtnrAndBin"
        entry = bridge_state.get("zones", {}).get(key, {}) if isinstance(bridge_state, dict) else {}
        if not entry:
            return False, f"{position}:missing_bridge_state"
        if str(entry.get("last_seen_state", "")).strip() != required_state:
            return False, f"{position}:bridge_state_not_{required_state}"
        session = entry.get("hybrid_session", {}) if isinstance(entry.get("hybrid_session", {}), dict) else {}
        if session.get("needs_reconcile", False):
            return False, f"{position}:needs_reconcile"
        if self.require_canonical and str(session.get("policy", "")).strip() not in {"hybrid_canonical", "hybrid_fg_canonical"}:
            return False, f"{position}:not_hybrid_canonical"
        if required_state == "occupied":
            actual_ctnr = str(session.get("actual_ctnr_code", "") or entry.get("last_bound_ctnr_code", "")).strip()
            if actual_ctnr and actual_ctnr.lower() != position.lower():
                return False, f"{position}:noncanonical_ctnr:{actual_ctnr}"
        return True, "ok"

    def _collect_position_states(self, cameras_payload: list[dict[str, Any]]) -> dict[str, str]:
        zone_index: dict[tuple[str, str], str] = {}
        for camera in cameras_payload:
            camera_id = str(camera.get("camera_id", "")).strip()
            camera_health = str(camera.get("camera_health", camera.get("health", "unknown"))).strip()
            for zone in camera.get("zones", []):
                if camera_health != "online" or str(zone.get("health", "unknown")).strip() != "online":
                    state = "unknown"
                else:
                    state = str(zone.get("state", "unknown")).strip()
                    if state not in {"occupied", "empty"}:
                        state = "unknown"
                zone_index[(camera_id, str(zone.get("zone_id", "")).strip())] = state

        states = {}
        for position, pos_cfg in self.config.get("positions", {}).items():
            key = (str(pos_cfg.get("camera_id", "")).strip(), str(pos_cfg.get("zone_id", "")).strip())
            states[str(position)] = zone_index.get(key, "unknown")
        return states

    def _empty_destination_positions(self, position_states: dict[str, str], batch: dict[str, Any]) -> list[str]:
        dest_cfg = self.config.get("routing", {}).get("destination_area", {})
        used_dests = {str(item) for item in batch.get("dispatched_dests", [])}
        return [
            str(position)
            for position in dest_cfg.get("positions", [])
            if str(position) not in used_dests and position_states.get(str(position)) == "empty"
        ]

    def _next_source(self, batch: dict[str, Any], position_states: dict[str, str]) -> str:
        dispatched = {str(item) for item in batch.get("dispatched_sources", [])}
        for source in batch.get("source_order", []):
            source = str(source)
            if source in dispatched:
                continue
            if position_states.get(source) == "occupied":
                return source
            return ""
        return ""

    @staticmethod
    def _all_sources_dispatched(batch: dict[str, Any]) -> bool:
        source_order = [str(item) for item in batch.get("source_order", [])]
        dispatched = {str(item) for item in batch.get("dispatched_sources", [])}
        return bool(source_order) and all(source in dispatched for source in source_order)

    def _source_call_code(self, source: str) -> str:
        for roadway in self.config.get("routing", {}).get("source_roadways", []):
            if source in [str(item) for item in roadway.get("positions", [])]:
                return str(roadway.get("call_code", "")).strip()
        return ""

    @staticmethod
    def _position_state(position_states: dict[str, str], position: str) -> str:
        return str(position_states.get(position, "unknown"))

    @staticmethod
    def _extract_task_status(response: dict[str, Any]) -> str:
        candidates = []
        data = response.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {}
        data_items = data if isinstance(data, list) else [data]
        for data_item in data_items:
            if isinstance(data_item, dict):
                candidates.extend(
                    data_item.get(key)
                    for key in ("taskStatus", "taskStatusName", "status", "state", "taskState", "taskStateName")
                )
        candidates.extend(response.get(key) for key in ("taskStatus", "taskStatusName", "status", "state"))
        for item in candidates:
            if item not in (None, ""):
                return str(item)
        return ""

    @staticmethod
    def _extract_own_task_response(response: dict[str, Any], task_code: str) -> dict[str, Any]:
        payload = dict(response or {})
        data = payload.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = []
        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
        else:
            items = []

        task_code_norm = str(task_code).strip().lower()
        if task_code_norm:
            for item in items:
                if str(item.get("taskCode", "")).strip().lower() == task_code_norm:
                    payload["data"] = item
                    return payload

        if len(items) == 1:
            payload["data"] = items[0]
            return payload

        payload["data"] = {}
        return payload

    def _load_control(self) -> dict[str, Any]:
        control = {
            "operation_mode": self.config.get("operation_mode", "manual"),
            "profile_id": self.config.get("profile_id", ""),
        }
        raw_path = str(self.config.get("control_state_path", "")).strip()
        if not raw_path:
            return control
        path = self.project_root / raw_path
        if not path.exists():
            return control
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return control
        if isinstance(payload, dict):
            control.update({key: value for key, value in payload.items() if value not in (None, "")})
        return control

    def set_control(self, payload: dict[str, Any], now_ts: float | None = None) -> dict[str, Any]:
        now_ts = float(now_ts if now_ts is not None else time.time())
        previous_control = self._load_control()
        operation_mode = str(payload.get("operation_mode", payload.get("mode", ""))).strip().lower()
        profile_id = str(payload.get("profile_id", self.config.get("profile_id", "PK_AB"))).strip()
        if operation_mode not in {"manual", "auto"}:
            return {
                "accepted": False,
                "reason": "operation_mode must be manual or auto",
                "control": self._load_control(),
            }
        if operation_mode == "auto" and profile_id not in self.allowed_profiles:
            return {
                "accepted": False,
                "reason": f"profile_id must be one of {sorted(self.allowed_profiles)}",
                "control": self._load_control(),
            }
        if operation_mode == "manual":
            profile_id = profile_id if profile_id in self.allowed_profiles else str(self.config.get("profile_id", "PK_AB"))

        control = {
            "operation_mode": operation_mode,
            "profile_id": profile_id,
            "updated_at": round(now_ts, 3),
            "updated_by": str(payload.get("updated_by", payload.get("source", "third_party_api"))).strip() or "third_party_api",
            "note": str(payload.get("note", "")).strip(),
        }
        raw_path = str(self.config.get("control_state_path", "")).strip()
        if raw_path:
            write_json_atomic(self.project_root / raw_path, control)
        if operation_mode == "manual":
            self.state.pop("batch", None)
            self._set_status("manual_mode", now_ts)
            self._save_state()
        elif operation_mode == "auto":
            self.state.pop("batch", None)
            self._set_status(f"auto_mode_requested:{profile_id}", now_ts)
            self._log_event(
                "auto_batch_reset",
                {
                    "profile_id": profile_id,
                    "previous_operation_mode": previous_control.get("operation_mode", ""),
                    "previous_profile_id": previous_control.get("profile_id", ""),
                },
                now_ts,
            )
            self._save_state()
        return {
            "accepted": True,
            "reason": "ok",
            "control": control,
            "state": self.public_status(),
        }

    def public_status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "dispatcher_id": self.dispatcher_id,
            "dry_run": self.dry_run,
            "control": self._load_control(),
            "state": self.state,
            "allowed_profiles": sorted(self.allowed_profiles),
            "require_bind_notify": self.require_bind_notify,
            "require_canonical": self.require_canonical,
            "callback_server_enabled": self.callback_server_enabled,
        }

    def query_agv_status(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        if not payload.get("agvCode") and self.query_status_agv_code:
            payload["agvCode"] = self.query_status_agv_code
        return self.client.query_agv_status(payload, req_code=str(payload.get("reqCode", "")) or None)

    def query_task_status(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        task_code = str(payload.get("taskCode", "")).strip()
        if not task_code:
            task_codes = payload.get("taskCodes", [])
            if isinstance(task_codes, list) and task_codes:
                task_code = str(task_codes[0]).strip()
        if not task_code:
            return {
                "code": "CONFIG_ERROR",
                "message": "taskCode or taskCodes[0] is required",
                "reqCode": str(payload.get("reqCode", "")),
                "reqTime": HikRcsClient.now_text(),
                "data": {},
            }
        payload.pop("taskCode", None)
        payload["taskCodes"] = [task_code]
        if not payload.get("agvCode") and self.query_status_agv_code:
            payload["agvCode"] = self.query_status_agv_code
        response = self.client.call_rpc("queryTaskStatus", payload, req_code=str(payload.get("reqCode", "")) or None)
        return self._extract_own_task_response(response, task_code)

    def _set_idle(self, reason: str, now_ts: float) -> None:
        if self.state.get("status") == reason and "batch" not in self.state:
            return
        self.state.pop("batch", None)
        self._set_status(reason, now_ts)
        self._save_state()

    def _set_status(self, status: str, now_ts: float) -> None:
        self.state["status"] = status
        self.state["updated_at"] = round(now_ts, 3)

    def _log_event(self, event: str, payload: dict[str, Any], now_ts: float) -> None:
        append_jsonl_rotating(
            self.event_log_path,
            {"event": event, "timestamp": round(now_ts, 3), "payload": payload},
            max_bytes=5 * 1024 * 1024,
            backup_count=5,
        )

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            logger.warning("[AUTO-DISPATCH] Invalid state file, reset auto dispatch state")
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_state(self) -> None:
        write_json_atomic(self.state_path, self.state)


class AutoDispatchControlServer:
    """Small HTTP API for third-party mode/profile control."""

    def __init__(self, config: dict[str, Any], dispatcher: AutoDispatcher) -> None:
        self.config = config
        self.dispatcher = dispatcher
        self.dispatchers: dict[str, AutoDispatcher] = {"amr": dispatcher}
        self.host = str(config.get("host", "0.0.0.0")).strip() or "0.0.0.0"
        self.port = int(config.get("port", 8023))
        self.base_path = str(config.get("base_path", "/service/rest/visionAutoDispatch")).rstrip("/")
        self.allowlist = self._parse_allowlist(config.get("allowlist", []))
        self.log_max_bytes = max(0, int(float(config.get("log_max_mb", 10.0)) * 1024 * 1024))
        self.log_backup_count = max(0, int(config.get("log_backup_count", 5)))
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def register_dispatcher(self, dispatcher_id: str, dispatcher: AutoDispatcher) -> None:
        """Expose another independent dispatch lane under this API server."""
        key = str(dispatcher_id).strip().lower()
        if not key or key == "amr":
            raise ValueError("dispatcher_id must be a non-default API namespace")
        self.dispatchers[key] = dispatcher

    def start(self) -> None:
        if self._server is not None:
            return
        self._server = ThreadingHTTPServer((self.host, self.port), self._build_handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        actual_port = int(self._server.server_address[1])
        logger.info("[AUTO-DISPATCH] Control API listening on http://%s:%s%s", self.host, actual_port, self.base_path)

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def _build_handler(self):
        outer = self

        class ControlHandler(BaseHTTPRequestHandler):
            server_version = "PIDVN-AUTO-DISPATCH/1.0"

            def do_GET(self) -> None:  # noqa: N802
                if not outer._client_allowed(self.client_address[0]):
                    self._write_json(403, outer._response("403", "forbidden by allowlist", "", {}))
                    return
                resolved_route = self._resolve_route(self.path)
                if resolved_route is not None and resolved_route[1] in {"health", "status"}:
                    dispatcher_id, route = resolved_route
                    payload = {"reqCode": "", "path": self.path}
                    response = outer._handle_route(dispatcher_id, route, payload)
                    outer._store_api_event(dispatcher_id, self.path, payload, response)
                    self._write_json(200, response)
                    return
                self._write_json(404, outer._response("404", "unsupported auto dispatch endpoint", "", {}))

            def do_POST(self) -> None:  # noqa: N802
                if not outer._client_allowed(self.client_address[0]):
                    req_code = ""
                    try:
                        req_code = str(self._read_json_body().get("reqCode", ""))
                    except Exception:
                        req_code = ""
                    response = outer._response("403", "forbidden by allowlist", req_code, {})
                    outer._store_api_event("amr", self.path, {"client_ip": self.client_address[0]}, response)
                    self._write_json(403, response)
                    return
                resolved_route = self._resolve_route(self.path)
                body = self._read_json_body()
                req_code = str(body.get("reqCode", ""))
                if resolved_route is None:
                    response = outer._response("404", "unsupported auto dispatch endpoint", req_code, {})
                    outer._store_api_event("amr", self.path, body, response)
                    self._write_json(404, response)
                    return
                dispatcher_id, route = resolved_route
                response = outer._handle_route(dispatcher_id, route, body)
                outer._store_api_event(dispatcher_id, self.path, body, response)
                status_code = 200 if str(response.get("code", "")) == "0" else 400
                self._write_json(status_code, response)

            def log_message(self, format_: str, *args) -> None:
                logger.debug("[AUTO-DISPATCH-API] " + format_, *args)

            def _resolve_route(self, path: str) -> tuple[str, str] | None:
                normalized = path.split("?", 1)[0].rstrip("/")
                route_suffixes = {
                    "health": "health",
                    "status": "status",
                    "getStatus": "status",
                    "setMode": "set_mode",
                    "queryAgvStatus": "query_agv_status",
                    "queryTaskStatus": "query_task_status",
                }
                for dispatcher_id in outer.dispatchers:
                    prefixes = [f"{outer.base_path}/{dispatcher_id}"]
                    if dispatcher_id == "amr":
                        prefixes.append(outer.base_path)
                    for suffix, route in route_suffixes.items():
                        for prefix in prefixes:
                            if normalized == f"{prefix}/{suffix}":
                                return dispatcher_id, route
                return None

            def _read_json_body(self) -> dict[str, Any]:
                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    content_length = 0
                raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    payload = {"raw": raw.decode("utf-8", errors="replace")}
                return payload if isinstance(payload, dict) else {"data": payload}

            def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return ControlHandler

    def _handle_route(self, dispatcher_id: str, route: str, payload: dict[str, Any]) -> dict[str, Any]:
        dispatcher = self.dispatchers[dispatcher_id]
        req_code = str(payload.get("reqCode", ""))
        if route == "health":
            return self._response("0", "successful", req_code, {"service": "auto_dispatch", "dispatcher_id": dispatcher_id, "status": "online"})
        if route == "status":
            return self._response("0", "successful", req_code, dispatcher.public_status())
        if route == "set_mode":
            result = dispatcher.set_control(payload)
            if result.get("accepted", False):
                return self._response("0", "successful", req_code, result)
            return self._response("CONFIG_ERROR", str(result.get("reason", "invalid control payload")), req_code, result)
        if route == "query_agv_status":
            result = dispatcher.query_agv_status(payload)
            return self._normalize_rcs_response(req_code=req_code, result=result)
        if route == "query_task_status":
            result = dispatcher.query_task_status(payload)
            return self._normalize_rcs_response(req_code=req_code, result=result)
        return self._response("404", "unsupported auto dispatch route", req_code, {})

    @staticmethod
    def _response(code: str, message: str, req_code: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "code": code,
            "message": message,
            "reqCode": req_code,
            "reqTime": HikRcsClient.now_text(),
            "data": data,
        }

    def _store_api_event(self, dispatcher_id: str, path: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> None:
        dispatcher = self.dispatchers.get(dispatcher_id, self.dispatcher)
        event = {
            "stored_at_ts": time.time(),
            "dispatcher_id": dispatcher_id,
            "path": path,
            "request": request_payload,
            "response": response_payload,
        }
        write_json_atomic(dispatcher.control_latest_path, event)
        append_jsonl_rotating(
            dispatcher.control_event_log_path,
            event,
            max_bytes=self.log_max_bytes,
            backup_count=self.log_backup_count,
        )

    @staticmethod
    def _parse_allowlist(raw_value: Any) -> set[str]:
        allowlist: set[str] = set()
        if isinstance(raw_value, list):
            for item in raw_value:
                value = str(item).strip()
                if value:
                    allowlist.add(value)
        return allowlist

    def _client_allowed(self, client_ip: str) -> bool:
        if not self.allowlist:
            return True
        client_ip = str(client_ip).strip()
        if not client_ip:
            return False
        if client_ip in self.allowlist:
            return True
        try:
            parsed = ip_address(client_ip)
        except ValueError:
            return False
        return str(parsed) in self.allowlist

    @staticmethod
    def _normalize_rcs_response(*, req_code: str, result: dict[str, Any]) -> dict[str, Any]:
        payload = dict(result or {})
        payload.setdefault("reqCode", req_code)
        payload.setdefault("reqTime", HikRcsClient.now_text())
        payload.setdefault("data", {})
        return payload
