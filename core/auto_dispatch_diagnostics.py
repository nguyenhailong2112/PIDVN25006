from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.auto_dispatch_ledger import write_json_atomic_local
from core.auto_dispatch_planner import AutoDispatchPlanner
from core.hik_rcs_task_client import HikRcsTaskClient


class AutoDispatchDiagnostics:
    """Preflight, doctor report, and deterministic simulator for Phase 2."""

    def __init__(self, auto_config: dict[str, Any], hik_config: dict[str, Any], project_root: str | Path) -> None:
        self.auto_config = auto_config or {}
        self.hik_config = hik_config or {}
        self.project_root = Path(project_root)
        self.output_dir = self.project_root / "outputs" / "runtime" / "auto_dispatch"

    def validate_config(self) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        info: list[str] = []

        enabled = bool(self.auto_config.get("enabled", False))
        dry_run = bool(self.auto_config.get("dry_run", True))
        mode = str(self.auto_config.get("mode", "disabled")).strip() or "disabled"
        if mode not in {"disabled", "semi_auto", "full_auto"}:
            errors.append(f"auto_dispatch.mode invalid: {mode}")
        if not enabled:
            warnings.append("auto_dispatch.enabled=false; Phase 2 will not submit or arm tasks.")
        if dry_run:
            warnings.append("auto_dispatch.dry_run=true; requests are not sent to RCS.")

        positions = self.auto_config.get("positions", {})
        if not isinstance(positions, dict) or not positions:
            errors.append("auto_dispatch.positions is empty or invalid.")
            positions = {}
        pk_order = [str(item) for item in self.auto_config.get("pk_pick_order", [])]
        fg_order = [str(item) for item in self.auto_config.get("fg_put_order", [])]
        errors.extend(self._duplicate_errors("pk_pick_order", pk_order))
        errors.extend(self._duplicate_errors("fg_put_order", fg_order))
        if not pk_order:
            errors.append("pk_pick_order is empty.")
        if not fg_order:
            errors.append("fg_put_order is empty.")
        for position in pk_order + fg_order:
            if position not in positions:
                errors.append(f"{position} is in order list but missing from positions.")
        for position, ref in positions.items():
            if not isinstance(ref, dict):
                errors.append(f"positions.{position} is not an object.")
                continue
            if not str(ref.get("camera_id", "")).strip() or not str(ref.get("zone_id", "")).strip():
                errors.append(f"positions.{position} requires camera_id and zone_id.")
            if position.startswith("PK_") and position not in pk_order:
                warnings.append(f"{position} is configured but not in pk_pick_order.")
            if position.startswith("FG_") and position not in fg_order:
                warnings.append(f"{position} is configured but not in fg_put_order.")

        mapping_by_position = self._enabled_bind_mappings_by_position()
        for position in pk_order + fg_order:
            mapping = mapping_by_position.get(position)
            if mapping is None:
                errors.append(f"{position} has no enabled bindCtnrAndBin mapping in hik_rcs.json.")
                continue
            ctnr_code = str(mapping.get("ctnr_code", "")).strip()
            if ctnr_code and ctnr_code != position:
                warnings.append(f"{position} mapping ctnr_code={ctnr_code}; canonical Phase 2 expects {position}.")
            if position.startswith("FG_") and bool(self.auto_config.get("require_fg_canonical", True)):
                policy = str(mapping.get("dispatch_policy", "")).strip()
                if policy != "hybrid_fg_canonical":
                    errors.append(f"{position} must use dispatch_policy=hybrid_fg_canonical for canonical FG control.")

        callback_cfg = self.hik_config.get("callback_server", {})
        if not isinstance(callback_cfg, dict):
            callback_cfg = {}
        callback_enabled = bool(callback_cfg.get("enabled", False))
        callback_base = str(callback_cfg.get("base_path", "")).rstrip("/")
        callback_port = int(callback_cfg.get("port", 0) or 0)
        if bool(self.auto_config.get("require_bind_notify", True)):
            if not callback_enabled:
                errors.append("require_bind_notify=true but hik_rcs.callback_server.enabled=false.")
            if not callback_base:
                errors.append("require_bind_notify=true but callback_server.base_path is empty.")
            if callback_port <= 0:
                errors.append("require_bind_notify=true but callback_server.port is invalid.")
        if callback_enabled:
            info.append(f"RCS Application Registration Base Path: {callback_base or '/service/rest'}")
            info.append(f"bindNotify notification path: {(callback_base or '/service/rest')}/bindNotify")
            info.append(f"agvCallback notification path: {(callback_base or '/service/rest')}/agvCallback")

        max_active = int(self.auto_config.get("max_active_tasks", 1) or 1)
        if max_active != 1:
            warnings.append("max_active_tasks should stay 1 for first production rollout.")

        if mode == "full_auto" or bool(self.auto_config.get("require_manual_interlock", True)):
            source = str(self.auto_config.get("manual_interlock_source", "")).strip()
            if not source or source == "TBD_BY_AGV":
                errors.append("manual_interlock_source is not configured.")
            elif source == "operator_command" and not str(self.auto_config.get("manual_lock_path", "")).strip():
                errors.append("manual_interlock_source=operator_command requires manual_lock_path.")

        payload_errors = self._sample_task_payload_errors(pk_order, fg_order)
        if payload_errors:
            target = warnings if dry_run else errors
            for item in payload_errors:
                target.append(f"task_template: {item}")

        return {
            "ok": not errors,
            "enabled": enabled,
            "mode": mode,
            "dry_run": dry_run,
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "summary": {
                "positions": len(positions),
                "pk_positions": len(pk_order),
                "fg_positions": len(fg_order),
                "enabled_bind_mappings": len(mapping_by_position),
            },
        }

    def doctor_report(
        self,
        *,
        cameras_payload: list[dict[str, Any]],
        bridge_state: dict[str, Any],
        active_records: list[dict[str, Any]],
        runtime_state: dict[str, Any],
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        now_ts = float(now_ts if now_ts is not None else time.time())
        planner = AutoDispatchPlanner(self.auto_config, self.hik_config)
        validation = self.validate_config()
        semi_plan = planner.evaluate(
            cameras_payload=cameras_payload,
            bridge_state=bridge_state,
            active_reservations=active_records,
            now_ts=now_ts,
            mode="semi_auto",
            manual_active=False,
        )
        full_plan = planner.evaluate(
            cameras_payload=cameras_payload,
            bridge_state=bridge_state,
            active_reservations=active_records,
            now_ts=now_ts,
            mode="full_auto",
            manual_active=self._manual_active(),
        )
        return {
            "generated_at_ts": round(now_ts, 3),
            "validation": validation,
            "runtime_state": runtime_state,
            "active_records": active_records,
            "manual_interlock_active": self._manual_active(),
            "plans": {
                "semi_auto": semi_plan,
                "full_auto": full_plan,
            },
            "vision_snapshot": self._vision_snapshot(cameras_payload, now_ts),
            "bridge_snapshot": self._bridge_snapshot(bridge_state),
            "callback_snapshot": self._callback_snapshot(),
            "site_ready": {
                "can_enable_phase2": validation["ok"],
                "can_real_submit": validation["ok"] and not bool(self.auto_config.get("dry_run", True)),
                "reason": "ok" if validation["ok"] else "fix validation.errors before production",
            },
        }

    def write_doctor_report(self, report: dict[str, Any], output_path: str | Path | None = None) -> Path:
        if output_path is None:
            stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(float(report.get("generated_at_ts", time.time()))))
            output_path = self.output_dir / "debug_reports" / f"doctor_{stamp}.json"
        return write_json_atomic_local(Path(output_path), report)

    def build_simulated_payload(self, scenario: str, now_ts: float | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        now_ts = float(now_ts if now_ts is not None else time.time())
        positions = self.auto_config.get("positions", {})
        if not isinstance(positions, dict):
            positions = {}
        pk_order = [str(item) for item in self.auto_config.get("pk_pick_order", [])]
        fg_order = [str(item) for item in self.auto_config.get("fg_put_order", [])]
        occupied: set[str] = set()
        empty: set[str] = set()
        unknown: set[str] = set()

        if scenario == "full_pk_empty_fg":
            occupied.update(pk_order)
            empty.update(fg_order)
        elif scenario == "fg_full":
            occupied.update(pk_order)
            occupied.update(fg_order)
        elif scenario == "pk_empty":
            empty.update(pk_order)
            empty.update(fg_order)
        elif scenario == "unknown_source":
            occupied.update(pk_order)
            empty.update(fg_order)
            if pk_order:
                unknown.add(pk_order[0])
        elif scenario == "fg_not_canonical":
            occupied.update(pk_order)
            occupied.update(fg_order)
        else:
            raise ValueError(f"unknown simulation scenario: {scenario}")

        camera_payload_by_id: dict[str, dict[str, Any]] = {}
        for position, ref in positions.items():
            if not isinstance(ref, dict):
                continue
            camera_id = str(ref.get("camera_id", ""))
            zone_id = str(ref.get("zone_id", ""))
            camera = camera_payload_by_id.setdefault(
                camera_id,
                {"camera_id": camera_id, "camera_health": "online", "timestamp": now_ts, "zones": []},
            )
            state = "unknown"
            health = "unknown"
            score = 0.0
            if position in occupied:
                state = "occupied"
                health = "online"
                score = 0.99
            elif position in empty:
                state = "empty"
                health = "online"
                score = 0.99
            if position in unknown:
                state = "unknown"
                health = "offline"
                score = 0.0
            camera["zones"].append(
                {
                    "zone_id": zone_id,
                    "position_code": position,
                    "state": state,
                    "health": health,
                    "score": score,
                    "occupied_since": now_ts if state == "occupied" else 0.0,
                }
            )
            if position in unknown:
                camera["camera_health"] = "online"

        bridge_state = self._simulated_bridge_state(occupied, canonical=(scenario != "fg_not_canonical"))
        return list(camera_payload_by_id.values()), bridge_state

    def simulate_plan(self, scenario: str, *, mode: str = "semi_auto", now_ts: float | None = None) -> dict[str, Any]:
        now_ts = float(now_ts if now_ts is not None else time.time())
        cameras_payload, bridge_state = self.build_simulated_payload(scenario, now_ts=now_ts)
        planner = AutoDispatchPlanner(self.auto_config, self.hik_config)
        plan = planner.evaluate(
            cameras_payload=cameras_payload,
            bridge_state=bridge_state,
            active_reservations=[],
            now_ts=now_ts,
            mode=mode,
            manual_active=False,
        )
        return {
            "scenario": scenario,
            "mode": mode,
            "plan": plan,
            "camera_count": len(cameras_payload),
            "bridge_zone_count": len(bridge_state.get("zones", {})),
        }

    def _sample_task_payload_errors(self, pk_order: list[str], fg_order: list[str]) -> list[str]:
        if not pk_order or not fg_order:
            return []
        client = HikRcsTaskClient(self.hik_config, self.project_root / "outputs" / "runtime")
        payload = client.build_task_payload(
            auto_config=self.auto_config,
            source_position=pk_order[0],
            dest_position=fg_order[0],
            task_code="VISION_PRECHECK_TASK",
            reservation_id="R_PRECHECK",
            batch_id="B_PRECHECK",
            mode="semi_auto",
        )
        return client.validate_task_payload(payload)

    def _enabled_bind_mappings_by_position(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for mapping in self.hik_config.get("mappings", []):
            if not isinstance(mapping, dict):
                continue
            if not bool(mapping.get("enabled", False)):
                continue
            if str(mapping.get("method", "")).strip() != "bindCtnrAndBin":
                continue
            position = str(mapping.get("position_code", "")).strip()
            if position:
                result[position] = mapping
        return result

    def _manual_active(self) -> bool:
        path_text = str(self.auto_config.get("manual_lock_path", "")).strip()
        if not path_text:
            return False
        path = Path(path_text)
        if not path.is_absolute():
            path = self.project_root / path
        payload = _load_json(path, default={})
        return bool(payload.get("active", False)) if isinstance(payload, dict) else False

    def _vision_snapshot(self, cameras_payload: list[dict[str, Any]], now_ts: float) -> dict[str, Any]:
        positions = self.auto_config.get("positions", {})
        if not isinstance(positions, dict):
            positions = {}
        camera_map = {str(item.get("camera_id", "")): item for item in cameras_payload if isinstance(item, dict)}
        rows: list[dict[str, Any]] = []
        for position, ref in positions.items():
            if not isinstance(ref, dict):
                continue
            camera_id = str(ref.get("camera_id", ""))
            zone_id = str(ref.get("zone_id", ""))
            camera = camera_map.get(camera_id, {})
            zone = _zone_for(camera, zone_id) if isinstance(camera, dict) else None
            camera_ts = float(camera.get("timestamp", 0.0) or 0.0) if isinstance(camera, dict) else 0.0
            rows.append(
                {
                    "position": position,
                    "camera_id": camera_id,
                    "zone_id": zone_id,
                    "camera_health": camera.get("camera_health", camera.get("health", "missing")) if isinstance(camera, dict) else "missing",
                    "age_sec": round(now_ts - camera_ts, 3) if camera_ts > 0.0 else None,
                    "state": zone.get("state", "missing") if zone else "missing",
                    "zone_health": zone.get("health", "missing") if zone else "missing",
                    "score": zone.get("score", None) if zone else None,
                }
            )
        return {
            "camera_count": len(camera_map),
            "position_count": len(rows),
            "positions": rows,
        }

    def _bridge_snapshot(self, bridge_state: dict[str, Any]) -> dict[str, Any]:
        zones = bridge_state.get("zones", {}) if isinstance(bridge_state, dict) else {}
        if not isinstance(zones, dict):
            zones = {}
        rows: list[dict[str, Any]] = []
        needs_reconcile = 0
        for key, entry in zones.items():
            if not isinstance(entry, dict):
                continue
            session = entry.get("hybrid_session", {})
            if not isinstance(session, dict):
                session = {}
            if bool(session.get("needs_reconcile", False)):
                needs_reconcile += 1
            rows.append(
                {
                    "key": key,
                    "observed_state": entry.get("observed_state", ""),
                    "last_bound_ctnr_code": entry.get("last_bound_ctnr_code", ""),
                    "owner": session.get("owner", ""),
                    "actual_ctnr_code": session.get("actual_ctnr_code", ""),
                    "needs_reconcile": bool(session.get("needs_reconcile", False)),
                }
            )
        return {"zone_count": len(rows), "needs_reconcile_count": needs_reconcile, "zones": rows}

    def _callback_snapshot(self) -> dict[str, Any]:
        callback_dir = self.project_root / "outputs" / "runtime" / "hik_rcs" / "callbacks"
        result: dict[str, Any] = {}
        for route in ("bindNotify", "agvCallback", "warnCallback"):
            path = callback_dir / f"{route}.jsonl"
            events = _load_jsonl_tail(path, max_items=20)
            latest = events[-1] if events else {}
            result[route] = {
                "path": str(path),
                "exists": path.exists(),
                "tail_count": len(events),
                "latest_stored_at_ts": latest.get("stored_at_ts", None) if isinstance(latest, dict) else None,
                "latest_path": latest.get("path", "") if isinstance(latest, dict) else "",
            }
        return result

    def _simulated_bridge_state(self, occupied_positions: set[str], *, canonical: bool) -> dict[str, Any]:
        mapping_by_position = self._enabled_bind_mappings_by_position()
        zones: dict[str, Any] = {}
        for position in occupied_positions:
            if not position.startswith("FG_"):
                continue
            mapping = mapping_by_position.get(position, {})
            mapping_id = str(mapping.get("mapping_id", "")).strip()
            key = mapping_id or f"{mapping.get('camera_id', '')}:{mapping.get('zone_id', '')}:{mapping.get('method', '')}"
            actual = position if canonical else f"PK_SIM_{position}"
            zones[key] = {
                "observed_state": "occupied",
                "last_bound_ctnr_code": actual,
                "hybrid_session": {
                    "owner": "canonical_fg" if canonical else "rcs_record",
                    "actual_ctnr_code": actual,
                    "needs_reconcile": not canonical,
                },
            }
        return {"zones": zones}

    @staticmethod
    def _duplicate_errors(name: str, values: list[str]) -> list[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for value in values:
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        return [f"{name} has duplicate value: {value}" for value in sorted(duplicates)]


def _load_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


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


def _zone_for(camera: dict[str, Any], zone_id: str) -> dict[str, Any] | None:
    for zone in camera.get("zones", []):
        if str(zone.get("zone_id", "")) == zone_id:
            return zone
    return None
