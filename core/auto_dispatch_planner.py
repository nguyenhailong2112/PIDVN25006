from __future__ import annotations

import time
from typing import Any


class AutoDispatchPlanner:
    """Selects the next PK source and FG destination without side effects."""

    def __init__(self, config: dict[str, Any], hik_config: dict[str, Any]) -> None:
        self.config = config or {}
        self.hik_config = hik_config or {}
        self.positions = dict(self.config.get("positions", {}))
        self.pk_pick_order = [str(item) for item in self.config.get("pk_pick_order", [])]
        self.fg_put_order = [str(item) for item in self.config.get("fg_put_order", [])]
        self.min_zone_score = float(self.config.get("min_zone_score", 0.8))
        self.vision_fresh_timeout_sec = float(self.config.get("vision_fresh_timeout_sec", 2.0))
        self.require_fg_canonical = bool(self.config.get("require_fg_canonical", True))
        self.require_manual_interlock = bool(self.config.get("require_manual_interlock", True))
        self.mapping_by_position = self._build_hik_mapping_by_position()

    def evaluate(
        self,
        *,
        cameras_payload: list[dict[str, Any]],
        bridge_state: dict[str, Any],
        active_reservations: list[dict[str, Any]],
        now_ts: float | None = None,
        mode: str = "semi_auto",
        manual_active: bool = False,
    ) -> dict[str, Any]:
        now_ts = float(now_ts if now_ts is not None else time.time())
        if mode == "full_auto" and self.require_manual_interlock and manual_active:
            return self._blocked("PAUSED_MANUAL", "manual interlock is active")
        if self._bridge_needs_reconcile(bridge_state):
            return self._blocked("FG_RECONCILE_REQUIRED", "HIK bridge has FG canonical reconcile pending")

        active_positions = self._active_positions(active_reservations)
        camera_map = self._camera_map(cameras_payload)

        source_result = self._select_source(camera_map, bridge_state, active_positions, now_ts)
        if not source_result.get("ok", False):
            return source_result
        dest_result = self._select_dest(camera_map, bridge_state, active_positions, now_ts)
        if not dest_result.get("ok", False):
            return dest_result

        return {
            "can_dispatch": True,
            "reason": "ok",
            "source": source_result["position"],
            "dest": dest_result["position"],
            "source_ref": self.positions.get(source_result["position"], {}),
            "dest_ref": self.positions.get(dest_result["position"], {}),
            "source_zone": source_result.get("zone", {}),
            "dest_zone": dest_result.get("zone", {}),
            "evaluated_at": round(now_ts, 3),
        }

    def verify_record(
        self,
        *,
        record: dict[str, Any],
        cameras_payload: list[dict[str, Any]],
        bridge_state: dict[str, Any],
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        now_ts = float(now_ts if now_ts is not None else time.time())
        camera_map = self._camera_map(cameras_payload)
        source = str(record.get("source_position", ""))
        dest = str(record.get("dest_position", ""))
        source_check = self._position_status(source, camera_map, now_ts)
        dest_check = self._position_status(dest, camera_map, now_ts)

        if not source_check.get("usable", False):
            return self._verify_failed("source_not_usable", source_check)
        if not dest_check.get("usable", False):
            return self._verify_failed("dest_not_usable", dest_check)
        if source_check.get("state") != "empty":
            return self._verify_failed("source_not_empty", source_check)
        if dest_check.get("state") != "occupied":
            return self._verify_failed("dest_not_occupied", dest_check)
        if self.require_fg_canonical and not self._is_fg_canonical(dest, bridge_state):
            return self._verify_failed("dest_not_canonical", {"position": dest})
        return {"verified": True, "reason": "ok", "verified_at": round(now_ts, 3)}

    def _select_source(
        self,
        camera_map: dict[str, dict[str, Any]],
        bridge_state: dict[str, Any],
        active_positions: set[str],
        now_ts: float,
    ) -> dict[str, Any]:
        for position in self.pk_pick_order:
            if position in active_positions:
                return self._blocked("BLOCKED_SOURCE_RESERVED", f"{position} is reserved", position=position)
            status = self._position_status(position, camera_map, now_ts)
            if not status.get("usable", False):
                return self._blocked("BLOCKED_SOURCE_UNKNOWN", status.get("reason", "source unusable"), position=position)
            state = status.get("state")
            if state == "occupied":
                return {"ok": True, "position": position, "zone": status.get("zone", {})}
            if state == "empty":
                continue
            return self._blocked("BLOCKED_SOURCE_UNKNOWN", f"{position} state={state}", position=position)
        return self._blocked("BLOCKED_NO_SOURCE", "no occupied PK source")

    def _select_dest(
        self,
        camera_map: dict[str, dict[str, Any]],
        bridge_state: dict[str, Any],
        active_positions: set[str],
        now_ts: float,
    ) -> dict[str, Any]:
        for position in self.fg_put_order:
            if position in active_positions:
                return self._blocked("BLOCKED_DEST_RESERVED", f"{position} is reserved", position=position)
            status = self._position_status(position, camera_map, now_ts)
            if not status.get("usable", False):
                return self._blocked("BLOCKED_DEST_UNKNOWN", status.get("reason", "dest unusable"), position=position)
            state = status.get("state")
            if state == "empty":
                return {"ok": True, "position": position, "zone": status.get("zone", {})}
            if state == "occupied":
                if self.require_fg_canonical and not self._is_fg_canonical(position, bridge_state):
                    return self._blocked("FG_NOT_CANONICAL", f"{position} occupied but not canonical", position=position)
                continue
            return self._blocked("BLOCKED_DEST_UNKNOWN", f"{position} state={state}", position=position)
        return self._blocked("BLOCKED_NO_DEST", "no empty FG destination")

    def _position_status(self, position: str, camera_map: dict[str, dict[str, Any]], now_ts: float) -> dict[str, Any]:
        ref = self.positions.get(position)
        if not isinstance(ref, dict):
            return {"usable": False, "reason": f"{position} missing from auto_dispatch positions"}
        camera_id = str(ref.get("camera_id", ""))
        zone_id = str(ref.get("zone_id", ""))
        camera = camera_map.get(camera_id)
        if camera is None:
            return {"usable": False, "reason": f"{camera_id} missing snapshot"}
        camera_health = str(camera.get("camera_health", camera.get("health", "unknown")))
        if camera_health != "online":
            return {"usable": False, "reason": f"{camera_id} health={camera_health}"}
        camera_ts = float(camera.get("timestamp", 0.0) or 0.0)
        if camera_ts > 0.0 and self.vision_fresh_timeout_sec > 0.0 and (now_ts - camera_ts) > self.vision_fresh_timeout_sec:
            return {"usable": False, "reason": f"{camera_id} stale {round(now_ts - camera_ts, 3)}s"}
        zone = self._zone_for(camera, zone_id)
        if zone is None:
            return {"usable": False, "reason": f"{camera_id}:{zone_id} missing zone"}
        state = str(zone.get("state", "unknown"))
        zone_health = str(zone.get("health", "unknown"))
        score = float(zone.get("score", 0.0) or 0.0)
        if state not in {"occupied", "empty"}:
            return {"usable": False, "reason": f"{position} state={state}", "zone": zone}
        if zone_health != "online":
            return {"usable": False, "reason": f"{position} zone_health={zone_health}", "zone": zone}
        if score < self.min_zone_score:
            return {"usable": False, "reason": f"{position} score={score}", "zone": zone}
        return {"usable": True, "state": state, "zone": zone, "camera": camera}

    @staticmethod
    def _camera_map(cameras_payload: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {str(item.get("camera_id", "")): item for item in cameras_payload if isinstance(item, dict)}

    @staticmethod
    def _zone_for(camera: dict[str, Any], zone_id: str) -> dict[str, Any] | None:
        for zone in camera.get("zones", []):
            if str(zone.get("zone_id", "")) == zone_id:
                return zone
        return None

    @staticmethod
    def _active_positions(active_reservations: list[dict[str, Any]]) -> set[str]:
        positions: set[str] = set()
        for record in active_reservations:
            positions.add(str(record.get("source_position", "")))
            positions.add(str(record.get("dest_position", "")))
        positions.discard("")
        return positions

    def _build_hik_mapping_by_position(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for mapping in self.hik_config.get("mappings", []):
            if not isinstance(mapping, dict):
                continue
            position_code = str(mapping.get("position_code", "")).strip()
            if position_code:
                result[position_code] = mapping
        return result

    def _bridge_entry_for_position(self, position: str, bridge_state: dict[str, Any]) -> dict[str, Any]:
        mapping = self.mapping_by_position.get(position, {})
        mapping_id = str(mapping.get("mapping_id", "")).strip()
        method = str(mapping.get("method", "")).strip()
        key = mapping_id or f"{mapping.get('camera_id', '')}:{mapping.get('zone_id', '')}:{method}"
        zones = bridge_state.get("zones", {}) if isinstance(bridge_state, dict) else {}
        entry = zones.get(key, {}) if isinstance(zones, dict) else {}
        return entry if isinstance(entry, dict) else {}

    def _is_fg_canonical(self, position: str, bridge_state: dict[str, Any]) -> bool:
        if not position.startswith("FG_"):
            return True
        entry = self._bridge_entry_for_position(position, bridge_state)
        session = entry.get("hybrid_session", {}) if isinstance(entry, dict) else {}
        if not isinstance(session, dict):
            session = {}
        if bool(session.get("needs_reconcile", False)):
            return False
        owner = str(session.get("owner", "")).strip()
        actual = str(session.get("actual_ctnr_code", "")).strip()
        last_bound = str(entry.get("last_bound_ctnr_code", "")).strip()
        if owner == "canonical_fg" and actual.lower() == position.lower():
            return True
        return last_bound.lower() == position.lower()

    @staticmethod
    def _bridge_needs_reconcile(bridge_state: dict[str, Any]) -> bool:
        zones = bridge_state.get("zones", {}) if isinstance(bridge_state, dict) else {}
        if not isinstance(zones, dict):
            return False
        for entry in zones.values():
            if not isinstance(entry, dict):
                continue
            session = entry.get("hybrid_session", {})
            if isinstance(session, dict) and session.get("needs_reconcile", False):
                return True
        return False

    @staticmethod
    def _blocked(reason: str, message: str, **extra: Any) -> dict[str, Any]:
        payload = {"can_dispatch": False, "ok": False, "reason": reason, "message": message}
        payload.update(extra)
        return payload

    @staticmethod
    def _verify_failed(reason: str, details: dict[str, Any]) -> dict[str, Any]:
        return {"verified": False, "reason": reason, "details": details}
