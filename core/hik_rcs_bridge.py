from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from core.hik_callback_server import HikCallbackServer
from core.hik_rcs_client import HikRcsClient
from core.file_utils import write_json_atomic
from core.logger_config import get_logger


logger = get_logger(__name__)


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class HikRcsBridge:
    """Maps Vision zone states to HIK RCS bind/unbind and safety calls."""

    SUPPORTED_METHODS = {"bindPodAndBerth", "bindPodAndMat", "bindCtnrAndBin", "lockPosition"}
    SUPPORTED_DISPATCH_POLICIES = {"vision_managed_static", "rcs_record_managed", "observe_only", "hybrid_fg_managed"}
    MAIN_BIND_SUPPRESSED_POLICIES = {"rcs_record_managed", "observe_only"}

    def __init__(self, config: dict, project_root: str | Path) -> None:
        self.config = config or {}
        self.project_root = Path(project_root)
        runtime_dir = self.project_root / "outputs" / "runtime"
        self.output_dir = runtime_dir / "hik_rcs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.output_dir / "bridge_state.json"

        self.enabled = bool(self.config.get("enabled", False))
        self.dry_run = bool(self.config.get("dry_run", True))
        self.require_online_health = bool(self.config.get("require_online_health", True))
        self.default_min_score = float(self.config.get("min_score", 0.0))
        self.retry_interval_sec = float(self.config.get("retry_interval_sec", 5.0))

        self.client = HikRcsClient(self.config, self.output_dir)
        self.callback_server = None
        self._validate_config()
        callback_cfg = self.config.get("callback_server", {})
        if callback_cfg.get("enabled", False):
            callback_cfg = dict(callback_cfg)
            callback_cfg.setdefault("token_code", self.config.get("token_code", ""))
            callback_cfg.setdefault("client_code", self.config.get("client_code", ""))
            callback_server = HikCallbackServer(callback_cfg, self.output_dir / "callbacks")
            try:
                callback_server.start()
            except Exception:
                logger.exception("[HIK-RCS] Failed to start callback server; outbound bridge remains active")
            else:
                self.callback_server = callback_server

        self.state = self._load_state()

    def close(self) -> None:
        self._save_state()
        if self.callback_server is not None:
            self.callback_server.stop()

    def sync(self, cameras_payload: list[dict], now_ts: float | None = None) -> None:
        if not self.enabled:
            return
        now_ts = float(now_ts if now_ts is not None else time.time())
        camera_map = {str(item.get("camera_id", "")): item for item in cameras_payload}

        dirty = False
        for mapping in self.config.get("mappings", []):
            if not mapping.get("enabled", False):
                continue
            if self._sync_mapping(mapping, camera_map, now_ts):
                dirty = True

        if dirty:
            self._save_state()

    def dispatch_zone_state(
        self,
        camera_payload: dict,
        zone_payload: dict,
        mapping: dict,
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        now_ts = float(now_ts if now_ts is not None else time.time())
        camera_map = {str(camera_payload.get("camera_id", "")): camera_payload}
        self._sync_mapping(mapping, camera_map, now_ts, forced_zone=zone_payload)
        return self._entry_for(mapping)

    def _sync_mapping(
        self,
        mapping: dict,
        camera_map: dict[str, dict],
        now_ts: float,
        forced_zone: dict[str, Any] | None = None,
    ) -> bool:
        mapping_key = self._mapping_key(mapping)
        entry = self._entry_for(mapping)
        entry.setdefault("mapping", mapping_key)
        camera_payload = camera_map.get(str(mapping.get("camera_id", "")))
        zone_payload = forced_zone or self._lookup_zone(camera_payload, str(mapping.get("zone_id", "")))
        if camera_payload is None or zone_payload is None:
            return self._handle_missing_payload(mapping, entry, now_ts, camera_payload=camera_payload, zone_payload=zone_payload)

        context = self._build_context(camera_payload, zone_payload, mapping)
        vision_state = self._resolve_effective_state(camera_payload, zone_payload, mapping)
        entry["last_seen_state"] = vision_state
        entry["last_seen_at"] = round(now_ts, 3)

        changed = False
        if vision_state == "unknown":
            changed |= self._handle_unknown(mapping, context, entry, now_ts)
        else:
            changed |= self._handle_known(mapping, context, entry, vision_state, now_ts)
        return changed

    def _handle_missing_payload(
        self,
        mapping: dict,
        entry: dict[str, Any],
        now_ts: float,
        *,
        camera_payload: dict[str, Any] | None,
        zone_payload: dict[str, Any] | None,
    ) -> bool:
        context = self._build_missing_context(mapping, camera_payload=camera_payload, zone_payload=zone_payload)
        entry["last_seen_state"] = "unknown"
        entry["last_seen_at"] = round(now_ts, 3)
        return self._handle_unknown(mapping, context, entry, now_ts)

    def _handle_unknown(self, mapping: dict, context: dict[str, Any], entry: dict[str, Any], now_ts: float) -> bool:
        method = str(mapping.get("method", "")).strip()
        if method == "lockPosition":
            return self._dispatch_lock_state(mapping, context, entry, now_ts, desired_state="disabled")
        action = str(mapping.get("unknown_action", "none")).strip()
        if action != "lockPosition":
            return False
        return self._dispatch_lock_state(mapping, context, entry, now_ts, desired_state="disabled")

    def _handle_known(
        self,
        mapping: dict,
        context: dict[str, Any],
        entry: dict[str, Any],
        vision_state: str,
        now_ts: float,
    ) -> bool:
        changed = False
        method = str(mapping.get("method", "")).strip()
        if method == "lockPosition":
            desired_state = "disabled" if vision_state == "occupied" else "enabled"
            return self._dispatch_lock_state(mapping, context, entry, now_ts, desired_state=desired_state)

        action = str(mapping.get("unknown_action", "none")).strip()
        if action == "lockPosition" and entry.get("lock_state") == "disabled":
            changed |= self._dispatch_lock_state(mapping, context, entry, now_ts, desired_state="enabled")
            if entry.get("lock_dispatch", {}).get("success") is False:
                return True

        dispatch = entry.setdefault("bind_dispatch", {})
        if method not in self.SUPPORTED_METHODS:
            logger.warning("[HIK-RCS] %s unsupported method=%s", self._mapping_key(mapping), method)
            return changed
        dispatch_policy = self._dispatch_policy(mapping)
        if dispatch_policy == "hybrid_fg_managed":
            return self._handle_hybrid_fg_mapping(
                mapping=mapping,
                context=context,
                entry=entry,
                vision_state=vision_state,
                now_ts=now_ts,
            ) or changed
        if self._main_bind_suppressed(method=method, dispatch_policy=dispatch_policy):
            return self._record_observed_policy_state(
                entry=entry,
                method=method,
                dispatch_policy=dispatch_policy,
                vision_state=vision_state,
                now_ts=now_ts,
            ) or changed

        ind_bind = "1" if vision_state == "occupied" else "0"
        desired_key = f"{method}:{ind_bind}"
        if not self._should_dispatch(dispatch, desired_key, now_ts):
            return changed
        req_code = self._prepare_dispatch(
            dispatch,
            desired_key,
            now_ts,
            mapping_key=self._mapping_key(mapping),
        )
        ctnr_code_override = self._resolve_ctnr_code_for_dispatch(
            method=method,
            entry=entry,
            mapping=mapping,
            context=context,
            ind_bind=ind_bind,
        )
        response = self._send_main_binding(
            method,
            mapping,
            context,
            req_code,
            ind_bind,
            ctnr_code_override=ctnr_code_override,
        )
        response = self._normalize_response(
            response=response,
            method=method,
            mapping=mapping,
            context=context,
            ind_bind=ind_bind,
        )
        self._commit_dispatch(dispatch, response, now_ts)
        bound_ctnr_hint = str(response.get("_bound_ctnr_code_hint", "")).strip()
        if bound_ctnr_hint:
            entry["last_bound_ctnr_code"] = bound_ctnr_hint
        if self.client.is_success(response):
            entry["bound_state"] = vision_state
            if method == "bindCtnrAndBin" and ind_bind == "1":
                used_ctnr = ctnr_code_override or self._resolve_field(mapping, "ctnr_code", context) or ""
                if used_ctnr:
                    entry["last_bound_ctnr_code"] = used_ctnr
            elif method == "bindCtnrAndBin" and ind_bind == "0":
                entry["last_bound_ctnr_code"] = ""
        changed = True
        return changed

    def _handle_hybrid_fg_mapping(
        self,
        *,
        mapping: dict,
        context: dict[str, Any],
        entry: dict[str, Any],
        vision_state: str,
        now_ts: float,
    ) -> bool:
        method = str(mapping.get("method", "")).strip()
        if method != "bindCtnrAndBin":
            logger.warning("[HIK-RCS] %s hybrid_fg_managed requires bindCtnrAndBin", self._mapping_key(mapping))
            return self._record_observed_policy_state(
                entry=entry,
                method=method,
                dispatch_policy="hybrid_fg_managed",
                vision_state=vision_state,
                now_ts=now_ts,
            )

        changed = self._record_observed_policy_state(
            entry=entry,
            method=method,
            dispatch_policy="hybrid_fg_managed",
            vision_state=vision_state,
            now_ts=now_ts,
        )
        entry["main_binding_suppressed"] = False
        session = entry.setdefault("hybrid_session", {})
        session["vision_state"] = vision_state
        session["updated_at"] = round(now_ts, 3)

        notify_hint = self._lookup_recent_container_hint(mapping, context, now_ts)
        if notify_hint:
            changed |= self._merge_hybrid_notify_hint(session, notify_hint)

        if vision_state == "occupied":
            changed |= self._handle_hybrid_occupied(mapping, context, entry, session, now_ts)
        elif vision_state == "empty":
            changed |= self._handle_hybrid_empty(mapping, context, entry, session, now_ts)
        return changed

    def _handle_hybrid_occupied(
        self,
        mapping: dict,
        context: dict[str, Any],
        entry: dict[str, Any],
        session: dict[str, Any],
        now_ts: float,
    ) -> bool:
        static_ctnr = self._resolve_field(mapping, "ctnr_code", context) or ""
        actual_ctnr = str(session.get("actual_ctnr_code", "")).strip()
        owner = str(session.get("owner", "")).strip()
        if owner == "rcs_record" and actual_ctnr:
            session["action"] = "suppress_static_bind_existing_rcs_record"
            return False

        return self._dispatch_hybrid_ctnr(
            mapping=mapping,
            context=context,
            entry=entry,
            session=session,
            now_ts=now_ts,
            ind_bind="1",
            ctnr_code=static_ctnr,
            desired_key=f"hybrid:bind:static:{static_ctnr}",
            expected_owner="manual_vision",
        )

    def _handle_hybrid_empty(
        self,
        mapping: dict,
        context: dict[str, Any],
        entry: dict[str, Any],
        session: dict[str, Any],
        now_ts: float,
    ) -> bool:
        static_ctnr = self._resolve_field(mapping, "ctnr_code", context) or ""
        owner = str(session.get("owner", "")).strip()
        actual_ctnr = str(session.get("actual_ctnr_code", "")).strip()
        if owner in {"manual_vision", ""}:
            ctnr_code = actual_ctnr or str(entry.get("last_bound_ctnr_code", "")).strip() or static_ctnr
        else:
            ctnr_code = actual_ctnr

        if not ctnr_code:
            previous_action = session.get("action")
            session["owner"] = owner or "unknown"
            session["action"] = "empty_without_known_ctnr_code"
            session["needs_reconcile"] = True
            return previous_action != session["action"]

        return self._dispatch_hybrid_ctnr(
            mapping=mapping,
            context=context,
            entry=entry,
            session=session,
            now_ts=now_ts,
            ind_bind="0",
            ctnr_code=ctnr_code,
            desired_key=f"hybrid:unbind:{owner or 'unknown'}:{ctnr_code}",
            expected_owner=owner or "unknown",
        )

    def _dispatch_hybrid_ctnr(
        self,
        *,
        mapping: dict,
        context: dict[str, Any],
        entry: dict[str, Any],
        session: dict[str, Any],
        now_ts: float,
        ind_bind: str,
        ctnr_code: str,
        desired_key: str,
        expected_owner: str,
    ) -> bool:
        dispatch = entry.setdefault("bind_dispatch", {})
        if not ctnr_code:
            session["action"] = "missing_ctnr_code"
            session["needs_reconcile"] = True
            return True
        if not self._should_dispatch(dispatch, desired_key, now_ts):
            return False

        req_code = self._prepare_dispatch(dispatch, desired_key, now_ts, mapping_key=self._mapping_key(mapping))
        response = self._send_main_binding(
            "bindCtnrAndBin",
            mapping,
            context,
            req_code,
            ind_bind,
            ctnr_code_override=ctnr_code,
        )
        response = self._normalize_hybrid_response(
            response=response,
            requested_ctnr=ctnr_code,
            ind_bind=ind_bind,
        )
        self._commit_dispatch(dispatch, response, now_ts)
        self._update_hybrid_session_after_response(
            entry=entry,
            session=session,
            response=response,
            requested_ctnr=ctnr_code,
            ind_bind=ind_bind,
            expected_owner=expected_owner,
            now_ts=now_ts,
        )
        return True

    def _send_main_binding(
        self,
        method: str,
        mapping: dict,
        context: dict[str, Any],
        req_code: str,
        ind_bind: str,
        *,
        ctnr_code_override: str | None = None,
    ) -> dict[str, Any]:
        if method == "bindPodAndBerth":
            pod_code = self._resolve_field(mapping, "pod_code", context)
            position_code = self._resolve_field(mapping, "position_code", context)
            if not pod_code or not position_code:
                return {"code": "CONFIG_ERROR", "message": "pod_code/position_code required", "reqCode": req_code}
            return self._dispatch(
                "bindPodAndBerth",
                lambda: self.client.bind_pod_and_berth(
                    req_code=req_code,
                    pod_code=pod_code,
                    position_code=position_code,
                    pod_dir=self._resolve_field(mapping, "pod_dir", context),
                    character_value=self._resolve_field(mapping, "character_value", context),
                    ind_bind=ind_bind,
                ),
                req_code,
                {
                    "podCode": pod_code,
                    "positionCode": position_code,
                    "podDir": self._resolve_field(mapping, "pod_dir", context),
                    "characterValue": self._resolve_field(mapping, "character_value", context),
                    "indBind": ind_bind,
                },
            )

        if method == "bindPodAndMat":
            pod_code = self._resolve_field(mapping, "pod_code", context)
            material_lot = self._resolve_field(mapping, "material_lot", context)
            if not pod_code or not material_lot:
                return {"code": "CONFIG_ERROR", "message": "pod_code/material_lot required", "reqCode": req_code}
            return self._dispatch(
                "bindPodAndMat",
                lambda: self.client.bind_pod_and_mat(
                    req_code=req_code,
                    pod_code=pod_code,
                    material_lot=material_lot,
                    ind_bind=ind_bind,
                ),
                req_code,
                {
                    "podCode": pod_code,
                    "materialLot": material_lot,
                    "indBind": ind_bind,
                },
            )

        if method == "bindCtnrAndBin":
            ctnr_code = ctnr_code_override or self._resolve_field(mapping, "ctnr_code", context)
            ctnr_typ = self._resolve_field(mapping, "ctnr_typ", context)
            stg_bin_code = self._resolve_field(mapping, "stg_bin_code", context)
            position_code = self._resolve_field(mapping, "position_code", context)
            if not ctnr_code or not ctnr_typ or not (stg_bin_code or position_code):
                return {
                    "code": "CONFIG_ERROR",
                    "message": "ctnr_code/ctnr_typ and one of stg_bin_code/position_code required",
                    "reqCode": req_code,
                }
            return self._dispatch(
                "bindCtnrAndBin",
                lambda: self.client.bind_ctnr_and_bin(
                    req_code=req_code,
                    ctnr_code=ctnr_code,
                    ctnr_typ=ctnr_typ,
                    stg_bin_code=stg_bin_code,
                    position_code=position_code,
                    bin_name=self._resolve_field(mapping, "bin_name", context),
                    character_value=self._resolve_field(mapping, "character_value", context),
                    ind_bind=ind_bind,
                ),
                req_code,
                {
                    "ctnrCode": ctnr_code,
                    "ctnrTyp": ctnr_typ,
                    "stgBinCode": stg_bin_code,
                    "positionCode": position_code,
                    "binName": self._resolve_field(mapping, "bin_name", context),
                    "characterValue": self._resolve_field(mapping, "character_value", context),
                    "indBind": ind_bind,
                },
            )

        return {"code": "CONFIG_ERROR", "message": f"unsupported method={method}", "reqCode": req_code}

    def _resolve_ctnr_code_for_dispatch(
        self,
        *,
        method: str,
        entry: dict[str, Any],
        mapping: dict[str, Any],
        context: dict[str, Any],
        ind_bind: str,
    ) -> str | None:
        if method != "bindCtnrAndBin":
            return None
        if ind_bind == "1":
            return None

        last_bound_ctnr = str(entry.get("last_bound_ctnr_code", "")).strip()
        if last_bound_ctnr:
            return last_bound_ctnr
        return self._resolve_field(mapping, "ctnr_code", context)

    @classmethod
    def _dispatch_policy(cls, mapping: dict[str, Any]) -> str:
        policy = str(mapping.get("dispatch_policy", "vision_managed_static")).strip()
        return policy or "vision_managed_static"

    @classmethod
    def _main_bind_suppressed(cls, *, method: str, dispatch_policy: str) -> bool:
        if method == "lockPosition":
            return False
        return dispatch_policy in cls.MAIN_BIND_SUPPRESSED_POLICIES

    @staticmethod
    def _record_observed_policy_state(
        *,
        entry: dict[str, Any],
        method: str,
        dispatch_policy: str,
        vision_state: str,
        now_ts: float,
    ) -> bool:
        previous_state = entry.get("observed_state")
        previous_policy = entry.get("dispatch_policy")
        previous_method = entry.get("observed_method")
        entry["observed_state"] = vision_state
        entry["observed_method"] = method
        entry["dispatch_policy"] = dispatch_policy
        entry["main_binding_suppressed"] = True
        entry["observed_at"] = round(now_ts, 3)
        return (
            previous_state != vision_state
            or previous_policy != dispatch_policy
            or previous_method != method
        )

    def _lookup_recent_container_hint(
        self,
        mapping: dict[str, Any],
        context: dict[str, Any],
        now_ts: float,
    ) -> dict[str, Any] | None:
        stg_bin_code = self._resolve_field(mapping, "stg_bin_code", context) or ""
        position_code = self._resolve_field(mapping, "position_code", context) or ""
        if not stg_bin_code and not position_code:
            return None
        max_age_sec = float(mapping.get("hybrid_callback_max_age_sec", self.config.get("hybrid_callback_max_age_sec", 3600.0)))
        callback_dir = self.output_dir / "callbacks"
        candidates: list[dict[str, Any]] = []
        candidates.extend(self._load_recent_callback_events(callback_dir / "bindNotify.jsonl", max_items=200))
        candidates.extend(self._load_recent_callback_events(callback_dir / "agvCallback.jsonl", max_items=200))
        candidates.sort(key=lambda item: float(item.get("stored_at_ts", 0.0) or 0.0), reverse=True)

        for event in candidates:
            stored_at = float(event.get("stored_at_ts", 0.0) or 0.0)
            if stored_at > 0.0 and (now_ts - stored_at) > max_age_sec:
                continue
            hint = self._container_hint_from_callback_event(event, stg_bin_code=stg_bin_code, position_code=position_code)
            if hint:
                hint["stored_at_ts"] = stored_at
                return hint
        return None

    @staticmethod
    def _load_recent_callback_events(path: Path, *, max_items: int) -> list[dict[str, Any]]:
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

    @staticmethod
    def _container_hint_from_callback_event(
        event: dict[str, Any],
        *,
        stg_bin_code: str,
        position_code: str,
    ) -> dict[str, Any] | None:
        route = str(event.get("route", "")).strip()
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            return None

        if route == "bindNotify":
            method = str(payload.get("method", "")).strip()
            if method != "bindCtnrAndBin":
                return None
            ind_bind = str(payload.get("indBind", "")).strip()
            params = payload.get("bindParam", [])
            if isinstance(params, dict):
                params = [params]
            if not isinstance(params, list):
                return None
            for item in params:
                if not isinstance(item, dict):
                    continue
                item_stg = str(item.get("stgBinCode", "") or item.get("stgBinCode".lower(), "")).strip()
                item_pos = str(item.get("positionCode", "") or item.get("berthCode", "")).strip()
                if (stg_bin_code and item_stg == stg_bin_code) or (position_code and item_pos == position_code):
                    ctnr_code = str(item.get("ctnrCode", "")).strip()
                    ctnr_typ = str(item.get("ctnrType", "") or item.get("ctnrTyp", "")).strip()
                    if ctnr_code:
                        return {
                            "source": "bindNotify",
                            "ind_bind": ind_bind,
                            "ctnr_code": ctnr_code,
                            "ctnr_typ": ctnr_typ,
                            "stg_bin_code": item_stg,
                            "position_code": item_pos,
                            "task_code": str(payload.get("taskCode", "")).strip(),
                        }
            return None

        if route == "agvCallback":
            callback_stg = str(payload.get("stgBinCode", "")).strip()
            callback_pos = str(payload.get("currentPositionCode", "") or payload.get("positionCode", "")).strip()
            if not ((stg_bin_code and callback_stg == stg_bin_code) or (position_code and callback_pos == position_code)):
                return None
            ctnr_code = str(payload.get("ctnrCode", "")).strip()
            if not ctnr_code:
                return None
            return {
                "source": "agvCallback",
                "ind_bind": "1" if str(payload.get("method", "")).strip() != "cancel" else "0",
                "ctnr_code": ctnr_code,
                "ctnr_typ": str(payload.get("ctnrTyp", "") or payload.get("ctnrType", "")).strip(),
                "stg_bin_code": callback_stg,
                "position_code": callback_pos,
                "task_code": str(payload.get("taskCode", "")).strip(),
                "callback_method": str(payload.get("method", "")).strip(),
            }
        return None

    @staticmethod
    def _merge_hybrid_notify_hint(session: dict[str, Any], hint: dict[str, Any]) -> bool:
        previous = {
            "owner": session.get("owner"),
            "actual_ctnr_code": session.get("actual_ctnr_code"),
            "actual_ctnr_source": session.get("actual_ctnr_source"),
            "notify_ind_bind": session.get("notify_ind_bind"),
        }
        if str(hint.get("ind_bind", "")).strip() == "0":
            session["last_unbind_notify"] = hint
            if str(session.get("actual_ctnr_code", "")).strip() == str(hint.get("ctnr_code", "")).strip():
                session["owner"] = ""
                session["actual_ctnr_code"] = ""
            return previous["owner"] != session.get("owner") or previous["actual_ctnr_code"] != session.get("actual_ctnr_code")

        session["owner"] = "rcs_record"
        session["actual_ctnr_code"] = str(hint.get("ctnr_code", "")).strip()
        session["actual_ctnr_typ"] = str(hint.get("ctnr_typ", "")).strip()
        session["actual_ctnr_source"] = str(hint.get("source", "")).strip()
        session["notify_ind_bind"] = str(hint.get("ind_bind", "")).strip()
        session["last_bind_notify"] = hint
        session["needs_reconcile"] = False
        return (
            previous["owner"] != session.get("owner")
            or previous["actual_ctnr_code"] != session.get("actual_ctnr_code")
            or previous["actual_ctnr_source"] != session.get("actual_ctnr_source")
            or previous["notify_ind_bind"] != session.get("notify_ind_bind")
        )

    def _normalize_hybrid_response(
        self,
        *,
        response: dict[str, Any],
        requested_ctnr: str,
        ind_bind: str,
    ) -> dict[str, Any]:
        if self.client.is_success(response):
            return response
        normalized = dict(response)
        existing_ctnr = self.client.extract_bound_ctnr_code(response)
        if existing_ctnr:
            normalized["_bound_ctnr_code_hint"] = existing_ctnr
            if ind_bind == "1" and existing_ctnr.strip().lower() != requested_ctnr.strip().lower():
                normalized["code"] = "0"
                normalized["message"] = f"hybrid accepted RCS-managed container: {existing_ctnr}"
                normalized["_hybrid_owner"] = "rcs_record"
                return normalized
            if existing_ctnr.strip().lower() == requested_ctnr.strip().lower():
                normalized["code"] = "0"
                normalized["message"] = f"already bound to desired container: {existing_ctnr}"
                return normalized

        message = str(response.get("message", "")).strip().lower()
        if "has been locked" in message or "has incomplete task" in message:
            normalized["_hybrid_owner"] = "rcs_record_pending"
            normalized["_non_retryable"] = True
            return normalized
        if ind_bind == "0" and ("not bound" in message or "doesnt bind" in message or "doesn't bind" in message):
            normalized["code"] = "0"
            normalized["message"] = "hybrid accepted already-unbound bin"
            normalized["_hybrid_already_clear"] = True
            return normalized
        if self._is_non_retryable_response(method="bindCtnrAndBin", response=response):
            normalized["_non_retryable"] = True
        return normalized

    @staticmethod
    def _update_hybrid_session_after_response(
        *,
        entry: dict[str, Any],
        session: dict[str, Any],
        response: dict[str, Any],
        requested_ctnr: str,
        ind_bind: str,
        expected_owner: str,
        now_ts: float,
    ) -> None:
        bound_hint = str(response.get("_bound_ctnr_code_hint", "")).strip()
        hybrid_owner = str(response.get("_hybrid_owner", "")).strip()
        success = str(response.get("code", "")) == "0"
        session["last_dispatch_at"] = round(now_ts, 3)
        session["last_dispatch_ind_bind"] = ind_bind
        session["last_dispatch_ctnr_code"] = requested_ctnr
        session["last_response_code"] = str(response.get("code", ""))
        session["last_response_message"] = str(response.get("message", ""))

        if ind_bind == "1":
            if hybrid_owner == "rcs_record" and bound_hint:
                session["owner"] = "rcs_record"
                session["actual_ctnr_code"] = bound_hint
                session["actual_ctnr_source"] = "rcs_response"
                session["action"] = "accepted_existing_rcs_record_bind"
                session["needs_reconcile"] = False
                entry["last_bound_ctnr_code"] = bound_hint
            elif hybrid_owner == "rcs_record_pending":
                session["owner"] = "rcs_record_pending"
                session["action"] = "rcs_locked_or_active_task"
                session["needs_reconcile"] = False
            elif success:
                session["owner"] = "manual_vision"
                session["actual_ctnr_code"] = requested_ctnr
                session["actual_ctnr_source"] = "vision_static"
                session["action"] = "manual_static_bind_success"
                session["needs_reconcile"] = False
                entry["bound_state"] = "occupied"
                entry["last_bound_ctnr_code"] = requested_ctnr
            else:
                session["action"] = "bind_failed_needs_reconcile"
                session["needs_reconcile"] = True
            return

        if success:
            session["owner"] = ""
            session["actual_ctnr_code"] = ""
            session["actual_ctnr_source"] = ""
            session["action"] = "unbind_success"
            session["needs_reconcile"] = False
            entry["bound_state"] = "empty"
            entry["last_bound_ctnr_code"] = ""
            return

        session["action"] = f"unbind_failed_{expected_owner or 'unknown'}"
        session["needs_reconcile"] = True

    def _send_lock_position(self, *, req_code: str, position_code: str, ind_bind: str) -> dict[str, Any]:
        return self._dispatch(
            "lockPosition",
            lambda: self.client.lock_position(req_code=req_code, position_code=position_code, ind_bind=ind_bind),
            req_code,
            {
                "positionCode": position_code,
                "indBind": ind_bind,
            },
        )

    def _dispatch_lock_state(
        self,
        mapping: dict,
        context: dict[str, Any],
        entry: dict[str, Any],
        now_ts: float,
        desired_state: str,
    ) -> bool:
        dispatch = entry.setdefault("lock_dispatch", {})
        invert_ind_bind = bool(mapping.get("invert_lock_position_ind_bind", False))
        desired_key = "lock:enable" if desired_state == "enabled" else "lock:disable"
        if invert_ind_bind:
            desired_key = f"{desired_key}:inverted"
        position_code = self._resolve_field(mapping, "lock_position_code", context) or self._resolve_field(mapping, "position_code", context)
        if not position_code:
            logger.warning("[HIK-RCS] %s missing position_code for lockPosition action", self._mapping_key(mapping))
            return False
        if not self._should_dispatch(dispatch, desired_key, now_ts):
            return False
        req_code = self._prepare_dispatch(
            dispatch,
            desired_key,
            now_ts,
            mapping_key=self._mapping_key(mapping),
        )
        ind_bind = "1" if desired_state == "enabled" else "0"
        if invert_ind_bind:
            ind_bind = "0" if ind_bind == "1" else "1"
        response = self._send_lock_position(req_code=req_code, position_code=position_code, ind_bind=ind_bind)
        response = self._normalize_response(
            response=response,
            method="lockPosition",
            mapping=mapping,
            context=context,
            ind_bind=ind_bind,
        )
        self._commit_dispatch(dispatch, response, now_ts)
        if self.client.is_success(response):
            entry["lock_state"] = desired_state
        return True

    def _dispatch(self, api_name: str, sender, req_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.dry_run:
            logger.info("[HIK-RCS] dry_run api=%s req=%s payload=%s", api_name, req_code, payload)
            return {"code": "0", "message": "dry_run", "reqCode": req_code, "data": ""}
        return sender()

    def _resolve_effective_state(self, camera_payload: dict, zone_payload: dict, mapping: dict) -> str:
        zone_state = str(zone_payload.get("state", "unknown"))
        zone_health = str(zone_payload.get("health", "unknown"))
        camera_health = str(camera_payload.get("camera_health", camera_payload.get("health", "unknown")))
        score = float(zone_payload.get("score", 0.0) or 0.0)
        min_score = float(mapping.get("min_score", self.default_min_score))

        if zone_state not in {"occupied", "empty"}:
            return "unknown"
        if self.require_online_health and (zone_health != "online" or camera_health != "online"):
            return "unknown"
        if score < min_score:
            return "unknown"
        return zone_state

    def _lookup_zone(self, camera_payload: dict | None, zone_id: str) -> dict[str, Any] | None:
        if camera_payload is None:
            return None
        for zone in camera_payload.get("zones", []):
            if str(zone.get("zone_id", "")) == zone_id:
                return zone
        return None

    def _build_context(self, camera_payload: dict, zone_payload: dict, mapping: dict) -> dict[str, Any]:
        return {
            "camera_id": camera_payload.get("camera_id", ""),
            "camera_name": camera_payload.get("camera_name", ""),
            "camera_type": camera_payload.get("camera_type", ""),
            "camera_health": camera_payload.get("camera_health", camera_payload.get("health", "unknown")),
            "camera_timestamp": camera_payload.get("timestamp", 0.0),
            "zone_id": zone_payload.get("zone_id", ""),
            "zone_state": zone_payload.get("state", "unknown"),
            "zone_health": zone_payload.get("health", "unknown"),
            "zone_score": zone_payload.get("score", 0.0),
            "binding": zone_payload.get("binding", "unknown"),
            "value": zone_payload.get("value", None),
            "mapping_method": mapping.get("method", ""),
        }

    def _build_missing_context(
        self,
        mapping: dict,
        *,
        camera_payload: dict[str, Any] | None,
        zone_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        resolved_camera = camera_payload or {
            "camera_id": mapping.get("camera_id", ""),
            "camera_name": "",
            "camera_type": "",
            "camera_health": "unknown",
            "timestamp": 0.0,
        }
        resolved_zone = zone_payload or {
            "zone_id": mapping.get("zone_id", ""),
            "state": "unknown",
            "health": "unknown",
            "score": 0.0,
            "binding": "unknown",
            "value": None,
        }
        return self._build_context(resolved_camera, resolved_zone, mapping)

    @staticmethod
    def _mapping_key(mapping: dict) -> str:
        mapping_id = str(mapping.get("mapping_id", "")).strip()
        if mapping_id:
            return mapping_id
        method = str(mapping.get("method", "")).strip()
        if method == "lockPosition":
            lock_position = str(mapping.get("lock_position_code", "") or mapping.get("position_code", "")).strip()
            return f"{mapping.get('camera_id', '')}:{mapping.get('zone_id', '')}:{method}:{lock_position}"
        return f"{mapping.get('camera_id', '')}:{mapping.get('zone_id', '')}:{method}"

    def _entry_for(self, mapping: dict) -> dict[str, Any]:
        zones = self.state.setdefault("zones", {})
        key = self._mapping_key(mapping)
        return zones.setdefault(key, {})

    def _resolve_field(self, mapping: dict, field_name: str, context: dict[str, Any]) -> str | None:
        template_value = mapping.get(f"{field_name}_template")
        raw_value = template_value if template_value is not None else mapping.get(field_name)
        if raw_value in (None, ""):
            return None
        return str(raw_value).format_map(_SafeFormatDict(context))

    def _should_dispatch(self, dispatch: dict[str, Any], desired_key: str, now_ts: float) -> bool:
        if dispatch.get("key") != desired_key:
            return True
        if dispatch.get("non_retryable", False):
            return False
        if not dispatch.get("success", False):
            return (now_ts - float(dispatch.get("attempt_ts", 0.0))) >= self.retry_interval_sec
        return False

    def _prepare_dispatch(
        self,
        dispatch: dict[str, Any],
        desired_key: str,
        now_ts: float,
        *,
        mapping_key: str,
    ) -> str:
        req_seed = f"{mapping_key}:{desired_key}:{time.time_ns()}"
        req_code = self.client.make_req_code(req_seed)
        dispatch["key"] = desired_key
        dispatch["req_code"] = req_code
        dispatch["attempt_ts"] = round(now_ts, 3)
        return str(dispatch.get("req_code", ""))

    def _normalize_response(
        self,
        *,
        response: dict[str, Any],
        method: str,
        mapping: dict[str, Any],
        context: dict[str, Any],
        ind_bind: str,
    ) -> dict[str, Any]:
        if self.client.is_success(response):
            return response

        message = str(response.get("message", "")).strip().lower()
        if "handled successfully" in message and "same reqcode" in message:
            normalized = dict(response)
            normalized["code"] = "0"
            return normalized

        if method == "bindCtnrAndBin" and ind_bind == "1":
            requested_ctnr = self._resolve_field(mapping, "ctnr_code", context) or ""
            existing_ctnr = self.client.extract_bound_ctnr_code(response)
            if requested_ctnr and existing_ctnr and requested_ctnr.strip().lower() == existing_ctnr.strip().lower():
                normalized = dict(response)
                normalized["code"] = "0"
                normalized["message"] = f"already bound to desired container: {existing_ctnr}"
                normalized["_bound_ctnr_code_hint"] = existing_ctnr
                return normalized
            if existing_ctnr:
                normalized = dict(response)
                normalized["_bound_ctnr_code_hint"] = existing_ctnr
                return normalized

        if self._is_non_retryable_response(method=method, response=response):
            normalized = dict(response)
            normalized["_non_retryable"] = True
            return normalized

        return response

    @staticmethod
    def _is_non_retryable_response(*, method: str, response: dict[str, Any]) -> bool:
        if str(response.get("code", "")).upper() == "CONFIG_ERROR":
            return True
        if str(response.get("code", "")) == "0":
            return False

        message = str(response.get("message", "")).strip().lower()
        if not message:
            return False

        lock_non_retryable_patterns = (
            "point code is not exist",
            "position code is not exist",
        )
        bind_non_retryable_patterns = (
            "has been locked",
            "has been frozen by user",
            "has bind container code",
            "not bound to this storage bin",
            "has incomplete task",
        )
        common_non_retryable_patterns = (
            "parameter error",
            "invalid parameter",
        )

        if any(token in message for token in common_non_retryable_patterns):
            return True
        if method == "lockPosition" and any(token in message for token in lock_non_retryable_patterns):
            return True
        if method == "bindCtnrAndBin" and any(token in message for token in bind_non_retryable_patterns):
            return True
        return False

    @staticmethod
    def _commit_dispatch(dispatch: dict[str, Any], response: dict[str, Any], now_ts: float) -> None:
        dispatch["success"] = str(response.get("code", "")) == "0"
        dispatch["non_retryable"] = bool(response.get("_non_retryable", False))
        clean_response = dict(response)
        clean_response.pop("_non_retryable", None)
        clean_response.pop("_bound_ctnr_code_hint", None)
        dispatch["response"] = clean_response
        dispatch["response_ts"] = round(now_ts, 3)

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"zones": {}}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            logger.warning("[HIK-RCS] Invalid state file, reset bridge state")
            return {"zones": {}}

    def _save_state(self) -> None:
        write_json_atomic(self.state_path, self.state)

    def _validate_config(self) -> None:
        if not self.enabled and not self.config.get("callback_server", {}).get("enabled", False):
            return

        if not self.config.get("host"):
            logger.warning("[HIK-RCS] host is empty in configs/hik_rcs.json")
        if not self.config.get("client_code"):
            logger.warning("[HIK-RCS] client_code is empty in configs/hik_rcs.json")

        enabled_mappings = [mapping for mapping in self.config.get("mappings", []) if mapping.get("enabled", False)]
        if self.enabled and not enabled_mappings:
            logger.warning("[HIK-RCS] Bridge enabled but no mapping is enabled")

        seen_mapping_keys: set[str] = set()
        for mapping in enabled_mappings:
            mapping_key = self._mapping_key(mapping)
            if mapping_key in seen_mapping_keys:
                logger.warning("[HIK-RCS] Duplicate enabled mapping key=%s", mapping_key)
            seen_mapping_keys.add(mapping_key)
            method = str(mapping.get("method", "")).strip()
            if method not in self.SUPPORTED_METHODS:
                logger.warning("[HIK-RCS] %s has unsupported method=%s", mapping_key, method)
            dispatch_policy = self._dispatch_policy(mapping)
            if dispatch_policy not in self.SUPPORTED_DISPATCH_POLICIES:
                logger.warning("[HIK-RCS] %s has unsupported dispatch_policy=%s", mapping_key, dispatch_policy)
            unknown_action = str(mapping.get("unknown_action", "none")).strip()
            if unknown_action not in {"none", "lockPosition"}:
                logger.warning("[HIK-RCS] %s has unsupported unknown_action=%s", mapping_key, unknown_action)
            if not mapping.get("camera_id") or not mapping.get("zone_id"):
                logger.warning("[HIK-RCS] Invalid mapping with missing camera_id/zone_id: %s", mapping)
            if method == "bindPodAndBerth":
                if not mapping.get("pod_code") or not mapping.get("position_code"):
                    logger.warning("[HIK-RCS] %s missing pod_code/position_code for bindPodAndBerth", mapping_key)
            elif method == "bindPodAndMat":
                if not mapping.get("pod_code") or not mapping.get("material_lot"):
                    logger.warning("[HIK-RCS] %s missing pod_code/material_lot for bindPodAndMat", mapping_key)
            elif method == "bindCtnrAndBin":
                if dispatch_policy not in self.MAIN_BIND_SUPPRESSED_POLICIES and (
                    not mapping.get("ctnr_code") or not mapping.get("ctnr_typ")
                ):
                    logger.warning("[HIK-RCS] %s missing ctnr_code/ctnr_typ for bindCtnrAndBin", mapping_key)
                if not mapping.get("stg_bin_code") and not mapping.get("position_code"):
                    logger.warning("[HIK-RCS] %s missing both stg_bin_code and position_code", mapping_key)
