import json
from pathlib import Path

from core.path_utils import ensure_exists, resolve_project_path
from core.types import CameraConfig, RuleConfig, ZoneConfig


def _coerce_str(value, fallback="") -> str:
    if value is None:
        return fallback
    return str(value)


def load_camera_configs(path: str | Path) -> list[CameraConfig]:
    path = ensure_exists(path, "Camera config")
    data = json.loads(path.read_text(encoding="utf-8"))
    configs: list[CameraConfig] = []

    for item in data:
        camera_type = _coerce_str(item.get("camera_type", "general_monitoring"))
        source_type = _coerce_str(item.get("source_type", "video")).lower()
        zone_config = _coerce_str(item.get("zone_config", ""))
        infer_every_n_frames = int(item.get("infer_every_n_frames", 1))
        enabled = bool(item.get("enabled", True))

        configs.append(
            CameraConfig(
                camera_id=_coerce_str(item.get("camera_id", "")),
                camera_type=camera_type,
                name=_coerce_str(item.get("name", "")),
                source_type=source_type,
                source_path=_coerce_str(item.get("source_path", "")),
                model_path=_coerce_str(item.get("model_path", "")),
                zone_config=zone_config,
                infer_every_n_frames=infer_every_n_frames,
                enabled=enabled,
            )
        )
    return configs


def load_zone_configs(path: str | Path) -> list[ZoneConfig]:
    path = ensure_exists(path, "Zone config")
    data = json.loads(path.read_text(encoding="utf-8"))
    zone_items = data["zones"]

    zones: list[ZoneConfig] = []
    for item in zone_items:
        polygon = [(float(x), float(y)) for x, y in item["polygon"]]
        zones.append(
            ZoneConfig(
                zone_id=item["zone_id"],
                target_object=item["target_object"],
                polygon=polygon,
            )
        )
    return zones


def load_rule_config(path: str | Path) -> RuleConfig:
    path = ensure_exists(path, "Rule config")
    data = json.loads(path.read_text(encoding="utf-8"))
    img_size = data.get("img_size")
    img_size = int(img_size) if img_size not in (None, "") else None

    return RuleConfig(
        spatial_method=str(data.get("spatial_method", "bbox_all_corners")),
        enter_window=int(data["enter_window"]),
        enter_count=int(data["enter_count"]),
        exit_window=int(data["exit_window"]),
        exit_count=int(data["exit_count"]),
        unknown_timeout_sec=float(data["unknown_timeout_sec"]),
        conf_threshold=float(data["conf_threshold"]),
        img_size=img_size,
        batch_size=int(data.get("batch_size", 1)),
        batch_timeout_ms=int(data.get("batch_timeout_ms", 0)),
    )


def load_json_dict(path: str | Path) -> dict:
    path = ensure_exists(path, "JSON config")
    return json.loads(path.read_text(encoding="utf-8"))
