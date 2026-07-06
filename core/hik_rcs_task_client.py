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
        path = list(template.get("positionCodePath", []) or [])
        if not path:
            path = [
                {
                    "positionCode": source_position,
                    "type": str(template.get("path_type_source", "TBD_BY_AGV")),
                },
                {
                    "positionCode": dest_position,
                    "type": str(template.get("path_type_dest", "TBD_BY_AGV")),
                },
            ]

        payload: dict[str, Any] = {
            "taskTyp": str(template.get("taskTyp", "")).strip(),
            "positionCodePath": path,
            "priority": str(auto_config.get("auto_priority", "")),
            "agvCode": str(template.get("agvCode", "")).strip(),
            "agvTyp": str(template.get("agvTyp", "")).strip(),
            "podCode": str(template.get("podCode", "")).strip(),
            "podTyp": str(template.get("podTyp", "")).strip(),
            "taskMode": str(template.get("taskMode", "")).strip(),
            "materialLot": str(template.get("materialLot", "")).strip(),
            "taskCode": task_code,
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
        optional_fields = ("ctnrTyp", "ctnrCode", "ctnrNum", "wbCode", "podDir", "materialType", "groupId", "positionSelStrategy")
        for field in optional_fields:
            value = template.get(field)
            if value not in (None, ""):
                payload[field] = value
        return {key: value for key, value in payload.items() if value not in (None, "")}

    def validate_task_payload(self, payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not str(payload.get("taskTyp", "")).strip() or str(payload.get("taskTyp", "")).startswith("TBD"):
            errors.append("taskTyp is not confirmed")
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
        if not str(payload.get("taskCode", "")).strip():
            errors.append("taskCode is empty")
        return errors

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
