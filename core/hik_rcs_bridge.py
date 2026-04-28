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
        desired_key = "lock:enable" if desired_state == "enabled" else "lock:disable"
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
        return f"{mapping.get('camera_id', '')}:{mapping.get('zone_id', '')}:{mapping.get('method', '')}"

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
                if not mapping.get("ctnr_code") or not mapping.get("ctnr_typ"):
                    logger.warning("[HIK-RCS] %s missing ctnr_code/ctnr_typ for bindCtnrAndBin", mapping_key)
                if not mapping.get("stg_bin_code") and not mapping.get("position_code"):
                    logger.warning("[HIK-RCS] %s missing both stg_bin_code and position_code", mapping_key)
