from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from core.auto_dispatch_types import stable_hash

class HikRcsTaskClient:
    """Task-level wrapper around HIK RCS scheduling APIs."""

    def __init__(self, hik_config: dict[str, Any], output_dir: str | Path) -> None:
        self.hik_config = hik_config or {}
        self.output_dir = Path(output_dir)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from core.hik_rcs_client import HikRcsClient

            self._client = HikRcsClient(self.hik_config, self.output_dir / "hik_rcs")
        return self._client

    def make_req_code(self, seed: str) -> str:
        return hashlib.md5(seed.encode("utf-8")).hexdigest()[:32]

    def build_task_payload(
        self,
        *,
        auto_config: dict[str, Any],
        source_position: str,
        dest_position: str,
        task_code: str,
        reservation_id: str,
        batch_id: str,
        mode: str,
    ) -> dict[str, Any]:
        template = dict(auto_config.get("task_template", {}))
        path_field = str(template.get("path_field", "positionCodePath")).strip() or "positionCodePath"

        payload: dict[str, Any] = {
            "taskTyp": str(template.get("taskTyp", "")).strip(),
            "priority": str(auto_config.get("auto_priority", "")),
            "agvCode": str(template.get("agvCode", "")).strip(),
            "agvTyp": str(template.get("agvTyp", "")).strip(),
            "podCode": str(template.get("podCode", "")).strip(),
            "podTyp": str(template.get("podTyp", "")).strip(),
            "taskMode": str(template.get("taskMode", "")).strip(),
            "materialLot": str(template.get("materialLot", "")).strip(),
            "data": json.dumps(
                {
                    "source": "vision_auto",
                    "mode": mode,
                    "batch_id": batch_id,
                    "reservation_id": reservation_id,
                    "from": source_position,
                    "to": dest_position,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
        if bool(template.get("send_task_code", True)):
            payload["taskCode"] = task_code
        payload[path_field] = self._build_path(
            template=template,
            auto_config=auto_config,
            path_field=path_field,
            source_position=source_position,
            dest_position=dest_position,
        )
        data_format = str(template.get("data_format", "json_string")).strip()
        if data_format == "object":
            payload["data"] = {
                "source": "vision_auto",
                "mode": mode,
                "batch_id": batch_id,
                "reservation_id": reservation_id,
                "from": source_position,
                "to": dest_position,
            }
        elif data_format == "empty_object":
            payload["data"] = {}
        optional_fields = (
            "interfaceName",
            "robotCode",
            "ctnrTyp",
            "ctnrCode",
            "ctnrNum",
            "wbCode",
            "podDir",
            "materialType",
            "groupId",
            "positionSelStrategy",
            "userCallCode",
            "needReqCode",
            "sFloor",
            "eFloor",
            "mapCode",
            "mapShortName",
        )
        for field in optional_fields:
            value = template.get(field)
            if value not in (None, ""):
                payload[field] = value
        return {key: value for key, value in payload.items() if value not in (None, "")}

    def validate_task_payload(self, payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not str(payload.get("taskTyp", "")).strip() or str(payload.get("taskTyp", "")).startswith("TBD"):
            errors.append("taskTyp is not confirmed")
        if "userCallCodePath" in payload:
            path = payload.get("userCallCodePath", [])
            if not isinstance(path, list) or len(path) < 2:
                errors.append("userCallCodePath requires at least source and destination")
            else:
                for index, item in enumerate(path):
                    value = str(item).strip()
                    if not value:
                        errors.append(f"userCallCodePath[{index}] is empty")
                    if value.startswith("TBD") or value.startswith("MISSING_CALL_CODE"):
                        errors.append(f"userCallCodePath[{index}] is not confirmed: {value}")
        else:
            path = payload.get("positionCodePath", [])
            if not isinstance(path, list) or len(path) < 2:
                errors.append("positionCodePath requires at least source and destination")
            else:
                for index, item in enumerate(path):
                    if not isinstance(item, dict):
                        errors.append(f"positionCodePath[{index}] is not an object")
                        continue
                    if not str(item.get("positionCode", "")).strip():
                        errors.append(f"positionCodePath[{index}].positionCode is empty")
                    if not str(item.get("type", "")).strip() or str(item.get("type", "")).startswith("TBD"):
                        errors.append(f"positionCodePath[{index}].type is not confirmed")
        return errors

    def _build_path(
        self,
        *,
        template: dict[str, Any],
        auto_config: dict[str, Any],
        path_field: str,
        source_position: str,
        dest_position: str,
    ) -> list[Any]:
        if path_field == "userCallCodePath":
            sequence = list(template.get("path_sequence", []) or ["{source}", "{dest}"])
            path: list[str] = []
            for item in sequence:
                text = str(item).strip()
                if text == "{source}":
                    path.append(self._resolve_call_code(auto_config, source_position))
                elif text == "{dest}":
                    path.append(self._resolve_call_code(auto_config, dest_position))
                else:
                    path.append(text)
            return path

        path = list(template.get("positionCodePath", []) or [])
        if path:
            rendered: list[dict[str, Any]] = []
            for item in path:
                if not isinstance(item, dict):
                    rendered.append(item)
                    continue
                rendered_item = dict(item)
                position_code = str(rendered_item.get("positionCode", ""))
                if position_code == "{source}":
                    rendered_item["positionCode"] = source_position
                elif position_code == "{dest}":
                    rendered_item["positionCode"] = dest_position
                rendered.append(rendered_item)
            return rendered

        return [
            {
                "positionCode": source_position,
                "type": str(template.get("path_type_source", "TBD_BY_AGV")),
            },
            {
                "positionCode": dest_position,
                "type": str(template.get("path_type_dest", "TBD_BY_AGV")),
            },
        ]

    @staticmethod
    def _resolve_call_code(auto_config: dict[str, Any], position: str) -> str:
        template = auto_config.get("task_template", {})
        if isinstance(template, dict):
            mapping = template.get("call_code_by_position", {})
            if isinstance(mapping, dict):
                value = str(mapping.get(position, "")).strip()
                if value:
                    return value
        positions = auto_config.get("positions", {})
        ref = positions.get(position, {}) if isinstance(positions, dict) else {}
        if isinstance(ref, dict):
            for field in ("rcs_call_code", "user_call_code", "path_code"):
                value = str(ref.get(field, "")).strip()
                if value:
                    return value
        if isinstance(template, dict) and bool(template.get("allow_position_code_as_call_code", False)):
            return position
        return f"MISSING_CALL_CODE:{position}"

    def payload_hash(self, payload: dict[str, Any]) -> str:
        return stable_hash(payload)

    def submit_task(self, *, payload: dict[str, Any], req_code: str, dry_run: bool) -> dict[str, Any]:
        if dry_run:
            return {
                "code": "0",
                "message": "dry_run",
                "reqCode": req_code,
                "data": payload.get("taskCode", ""),
                "_dry_run": True,
            }
        return self.client.call_rpc("genAgvSchedulingTask", payload, req_code=req_code)

    def query_task_status(
        self,
        *,
        task_code: str,
        req_code: str | None = None,
        dry_run: bool = False,
        dry_run_status: str = "2",
    ) -> dict[str, Any]:
        if dry_run:
            return {
                "code": "0",
                "message": "dry_run",
                "reqCode": req_code or "",
                "data": [
                    {
                        "taskCode": task_code,
                        "taskStatus": str(dry_run_status),
                        "agvCode": "",
                        "taskTyp": "",
                    }
                ],
                "_dry_run": True,
            }
        return self.client.call_rpc("queryTaskStatus", {"taskCodes": [task_code]}, req_code=req_code)
