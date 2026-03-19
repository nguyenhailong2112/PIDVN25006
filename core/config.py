import json
import os
from pathlib import Path

from core.path_utils import ensure_exists, resolve_project_path
from core.types import CameraConfig, RuleConfig, ZoneConfig


def _coerce_str(value, fallback="") -> str:
    if value is None:
        return fallback
    return str(value)


def _expand_env(value: str) -> str:
    if not value:
        return value
    return os.path.expandvars(value)


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
                source_path=_expand_env(_coerce_str(item.get("source_path", ""))),
                model_path=_expand_env(_coerce_str(item.get("model_path", ""))),
                zone_config=_expand_env(zone_config),
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
        max_pending_requests=int(data.get("max_pending_requests", 0)),
    )


def load_json_dict(path: str | Path) -> dict:
    path = ensure_exists(path, "JSON config")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_camera_configs(configs: list[CameraConfig]) -> None:
    errors = []
    for cfg in configs:
        if not cfg.camera_id:
            errors.append("camera_id is required")
        if not cfg.name:
            errors.append(f"{cfg.camera_id}: name is required")
        if cfg.source_type not in {"rtsp", "live", "video"}:
            errors.append(f"{cfg.camera_id}: invalid source_type={cfg.source_type}")
        if cfg.source_type == "video":
            try:
                ensure_exists(cfg.source_path, f"{cfg.camera_id} source_path")
            except FileNotFoundError as exc:
                errors.append(str(exc))
        if cfg.model_path:
            try:
                ensure_exists(cfg.model_path, f"{cfg.camera_id} model_path")
            except FileNotFoundError as exc:
                errors.append(str(exc))
        if cfg.camera_type in {"trolley_slot", "pallet_slot"}:
            if not cfg.zone_config:
                errors.append(f"{cfg.camera_id}: zone_config required for slot camera")
            else:
                try:
                    ensure_exists(cfg.zone_config, f"{cfg.camera_id} zone_config")
                except FileNotFoundError as exc:
                    errors.append(str(exc))

    if errors:
        raise ValueError("Config validation failed:\n- " + "\n- ".join(errors))


def validate_rule_config(rule_cfg: RuleConfig) -> None:
    errors = []
    if rule_cfg.enter_window <= 0 or rule_cfg.exit_window <= 0:
        errors.append("enter_window/exit_window must be > 0")
    if rule_cfg.enter_count <= 0 or rule_cfg.exit_count <= 0:
        errors.append("enter_count/exit_count must be > 0")
    if rule_cfg.unknown_timeout_sec <= 0:
        errors.append("unknown_timeout_sec must be > 0")
    if rule_cfg.conf_threshold < 0 or rule_cfg.conf_threshold > 1:
        errors.append("conf_threshold must be in [0,1]")
    if errors:
        raise ValueError("Rule config validation failed:\n- " + "\n- ".join(errors))


def validate_gui_config(gui_cfg: dict) -> None:
    errors = []
    for key in ("grid_rows", "grid_cols", "cell_min_width", "cell_min_height"):
        if key not in gui_cfg:
            errors.append(f"gui.json missing {key}")
    if errors:
        raise ValueError("GUI config validation failed:\n- " + "\n- ".join(errors))
