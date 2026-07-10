from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def merge_site_call_codes(auto_config: dict[str, Any], project_root: str | Path) -> dict[str, Any]:
    """Merge optional onsite call-code mapping into auto_dispatch config."""
    merged = json.loads(json.dumps(auto_config or {}, ensure_ascii=False))
    template = merged.setdefault("task_template", {})
    if not isinstance(template, dict):
        template = {}
        merged["task_template"] = template
    call_codes: dict[str, str] = {}
    external = load_site_call_codes(merged, project_root)
    for position, value in external.items():
        value = str(value).strip()
        if value:
            call_codes[str(position).strip()] = value
    template["call_code_by_position"] = call_codes
    return merged


def load_site_call_codes(auto_config: dict[str, Any], project_root: str | Path) -> dict[str, str]:
    template = auto_config.get("task_template", {}) if isinstance(auto_config, dict) else {}
    if not isinstance(template, dict):
        template = {}
    path_text = str(template.get("call_code_map_path", "") or auto_config.get("call_code_map_path", "") or "").strip()
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.is_absolute():
        path = Path(project_root) / path
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("call_code_by_position"), dict):
        payload = payload["call_code_by_position"]
    if not isinstance(payload, dict):
        return {}
    return {str(key).strip(): str(value).strip() for key, value in payload.items() if str(key).strip()}


def build_call_code_template(auto_config: dict[str, Any], hik_config: dict[str, Any]) -> dict[str, Any]:
    positions = auto_config.get("positions", {}) if isinstance(auto_config, dict) else {}
    if not isinstance(positions, dict):
        positions = {}
    pk_order = [str(item) for item in auto_config.get("pk_pick_order", [])]
    fg_order = [str(item) for item in auto_config.get("fg_put_order", [])]
    ordered = pk_order + fg_order
    template = auto_config.get("task_template", {}) if isinstance(auto_config, dict) else {}
    existing = template.get("call_code_by_position", {}) if isinstance(template, dict) else {}
    if not isinstance(existing, dict):
        existing = {}
    mapping_by_position = _hik_mapping_by_position(hik_config)
    rows: list[dict[str, Any]] = []
    call_code_by_position: dict[str, str] = {}
    for position in ordered:
        ref = positions.get(position, {})
        hik = mapping_by_position.get(position, {})
        call_code = str(existing.get(position, "")).strip() if isinstance(existing, dict) else ""
        call_code_by_position[position] = call_code
        rows.append(
            {
                "position_code": position,
                "area": ref.get("area", "") if isinstance(ref, dict) else "",
                "camera_id": ref.get("camera_id", "") if isinstance(ref, dict) else "",
                "zone_id": ref.get("zone_id", "") if isinstance(ref, dict) else "",
                "stg_bin_code": hik.get("stg_bin_code", "") if isinstance(hik, dict) else "",
                "ctnr_code": hik.get("ctnr_code", "") if isinstance(hik, dict) else "",
                "note": "Reference only. Fill call_code_by_position above, not rows.",
            }
        )
    return {
        "version": 1,
        "description": "Site mapping for Vision Phase 2 genAgvSchedulingTask userCallCodePath.",
        "call_code_by_position": call_code_by_position,
        "rows": rows,
    }


def _hik_mapping_by_position(hik_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in hik_config.get("mappings", []) if isinstance(hik_config, dict) else []:
        if not isinstance(item, dict):
            continue
        position = str(item.get("position_code", "")).strip()
        if position:
            result[position] = item
    return result
