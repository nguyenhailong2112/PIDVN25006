import json
import os
from pathlib import Path

from core.path_utils import ensure_exists
from core.types import CameraConfig, ElevatorClassifierConfig, ElevatorVisionConfig, IngestConfig, RuleConfig, ZoneConfig


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
    data = json.loads(path.read_text(encoding="utf-8-sig"))
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
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return _load_zone_configs_from_data(data, path)


def _load_zone_configs_from_data(
    data: dict,
    path: Path,
    default_polygon: list[tuple[float, float]] | None = None,
    default_target_object: str | None = None,
    default_spatial_method: str | None = None,
) -> list[ZoneConfig]:
    zone_items = data["zones"]
    allowed_spatial_methods = {"bbox_center", "bbox_all_corners", "bbox_intersects", ""}

    zones: list[ZoneConfig] = []
    for item in zone_items:
        spatial_method = _coerce_str(item.get("spatial_method", default_spatial_method or ""))
        if spatial_method not in allowed_spatial_methods:
            raise ValueError(f"Unsupported zone spatial_method={spatial_method} in {path}")
        target_object = _coerce_str(item.get("target_object", default_target_object or "")).strip()
        if not target_object:
            raise ValueError(f"Zone target_object is required in {path}")
        raw_polygon = item.get("polygon")
        if raw_polygon is None:
            if default_polygon is None:
                raise ValueError(f"Zone polygon is required in {path}")
            polygon = list(default_polygon)
        else:
            polygon = [(float(x), float(y)) for x, y in raw_polygon]
        zones.append(
            ZoneConfig(
                zone_id=item["zone_id"],
                target_object=target_object,
                polygon=polygon,
                spatial_method=spatial_method or None,
            )
        )
    return zones


def _load_elevator_classifier_config(name: str, data: dict) -> ElevatorClassifierConfig:
    roi = [(float(x), float(y)) for x, y in data["roi"]]
    labels = [_coerce_str(label).strip().lower() for label in data.get("labels", [])]
    return ElevatorClassifierConfig(
        name=name,
        model_path=_expand_env(_coerce_str(data.get("model_path", ""))),
        roi=roi,
        labels=labels,
    )


def load_elevator_vision_config(path: str | Path) -> ElevatorVisionConfig:
    path = ensure_exists(path, "Elevator vision config")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    vision_data = data.get("elevator_vision", data)
    return ElevatorVisionConfig(
        enabled=bool(vision_data.get("enabled", True)),
        img_size=int(vision_data.get("img_size", 224)),
        floor=_load_elevator_classifier_config("floor", vision_data["floor"]),
        gate=_load_elevator_classifier_config("gate", vision_data["gate"]),
        camera_id=_coerce_str(data.get("camera_id", "")),
    )


def load_elevator_zone_configs(path: str | Path) -> tuple[ElevatorVisionConfig, list[ZoneConfig]]:
    path = ensure_exists(path, "Elevator zone config")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if "elevator_vision" not in data:
        raise ValueError(f"elevator_vision is required in {path}")
    config = load_elevator_vision_config(path)
    zones = _load_zone_configs_from_data(
        data,
        path,
        default_polygon=config.floor.roi,
        default_target_object="*",
        default_spatial_method="bbox_intersects",
    )
    return config, zones


def load_rule_config(path: str | Path) -> RuleConfig:
    path = ensure_exists(path, "Rule config")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    img_size = data.get("img_size")
    img_size = int(img_size) if img_size not in (None, "") else None

    return RuleConfig(
        spatial_method=str(data.get("spatial_method", "bbox_intersects")),
        enter_window=int(data["enter_window"]),
        enter_count=int(data["enter_count"]),
        exit_window=int(data["exit_window"]),
        exit_count=int(data["exit_count"]),
        unknown_timeout_sec=float(data["unknown_timeout_sec"]),
        conf_threshold=float(data["conf_threshold"]),
        img_size=img_size,
        batch_size=int(data.get("batch_size", 1)),
        enter_confirm_sec=float(data.get("enter_confirm_sec", 0.0)),
        exit_confirm_sec=float(data.get("exit_confirm_sec", 0.0)),
        occupied_hold_sec=float(data.get("occupied_hold_sec", 0.0)),
    )

def load_ingest_config(path: str | Path) -> IngestConfig:
    path = ensure_exists(path, "Ingest config")
    data = json.loads(path.read_text(encoding="utf-8-sig"))

    return IngestConfig(
        stream_profile=str(data.get("stream_profile", "main")).lower(),
        latest_frame_only=bool(data.get("latest_frame_only", True)),
        reader_output_fps=float(data.get("reader_output_fps", 10.0)),
        buffer_size=int(data.get("buffer_size", 1)),
        reconnect_delay_sec=float(data.get("reconnect_delay_sec", 1.0)),
        rtsp_transport=str(data.get("rtsp_transport", "tcp")).lower(),
        open_timeout_msec=int(data.get("open_timeout_msec", 2000)),
        read_timeout_msec=int(data.get("read_timeout_msec", 1000)),
        skip_sleep_ms=int(data.get("skip_sleep_ms", 2)),
    )

def load_json_dict(path: str | Path) -> dict:
    path = ensure_exists(path, "JSON config")
    return json.loads(path.read_text(encoding="utf-8-sig"))


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
        if cfg.zone_config:
            try:
                ensure_exists(cfg.zone_config, f"{cfg.camera_id} zone_config")
            except FileNotFoundError as exc:
                errors.append(str(exc))
        elif cfg.camera_type in {"trolley_slot", "pallet_slot"}:
            errors.append(f"{cfg.camera_id}: zone_config required for slot camera")

    if errors:
        raise ValueError("Config validation failed:\n- " + "\n- ".join(errors))


def validate_rule_config(rule_cfg: RuleConfig) -> None:
    errors = []
    if rule_cfg.spatial_method not in {"bbox_center", "bbox_all_corners", "bbox_intersects"}:
        errors.append("spatial_method must be one of: bbox_center, bbox_all_corners, bbox_intersects")
    if rule_cfg.enter_window <= 0 or rule_cfg.exit_window <= 0:
        errors.append("enter_window/exit_window must be > 0")
    if rule_cfg.enter_count <= 0 or rule_cfg.exit_count <= 0:
        errors.append("enter_count/exit_count must be > 0")
    if rule_cfg.unknown_timeout_sec <= 0:
        errors.append("unknown_timeout_sec must be > 0")
    if rule_cfg.enter_confirm_sec < 0:
        errors.append("enter_confirm_sec must be >= 0")
    if rule_cfg.exit_confirm_sec < 0:
        errors.append("exit_confirm_sec must be >= 0")
    if rule_cfg.occupied_hold_sec < 0:
        errors.append("occupied_hold_sec must be >= 0")
    if rule_cfg.occupied_hold_sec > 0 and rule_cfg.exit_confirm_sec > 0 and rule_cfg.occupied_hold_sec < rule_cfg.exit_confirm_sec:
        errors.append("occupied_hold_sec should be >= exit_confirm_sec")
    if rule_cfg.conf_threshold < 0 or rule_cfg.conf_threshold > 1:
        errors.append("conf_threshold must be in [0,1]")
    if errors:
        raise ValueError("Rule config validation failed:\n- " + "\n- ".join(errors))


def validate_elevator_vision_config(config: ElevatorVisionConfig) -> None:
    errors = []
    if config.img_size <= 0:
        errors.append("img_size must be > 0")
    for classifier in (config.floor, config.gate):
        if not classifier.model_path:
            errors.append(f"{classifier.name}: model_path is required")
        if len(classifier.roi) != 4:
            errors.append(f"{classifier.name}: roi must contain exactly 4 points")
        for x, y in classifier.roi:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                errors.append(f"{classifier.name}: roi points must be normalized to [0,1]")
                break
        labels = set(classifier.labels)
        if classifier.name == "floor" and labels != {"empty", "occupied"}:
            errors.append("floor labels must be exactly: empty, occupied")
        if classifier.name == "gate" and labels != {"ok", "ng"}:
            errors.append("gate labels must be exactly: ok, ng")
    if errors:
        raise ValueError("Elevator vision config validation failed:\n- " + "\n- ".join(errors))


def validate_elevator_runtime_config(camera_configs: list[CameraConfig]) -> None:
    elevator_cameras = [cfg for cfg in camera_configs if cfg.camera_type == "elevator"]
    if not elevator_cameras:
        return

    errors = []
    for cfg in elevator_cameras:
        if cfg.model_path.strip():
            errors.append(f"{cfg.camera_id}: elevator model_path must be configured in its zone_config elevator_vision block, not configs/cameras.json")
        if not cfg.zone_config.strip():
            errors.append(f"{cfg.camera_id}: zone_config is required for elevator RCS mapping")
            continue
        try:
            config, _ = load_elevator_zone_configs(cfg.zone_config)
            validate_elevator_vision_config(config)
            if config.camera_id and config.camera_id != cfg.camera_id:
                errors.append(f"{cfg.camera_id}: zone_config camera_id must match camera config, got {config.camera_id}")
            if not config.enabled:
                errors.append(f"{cfg.camera_id}: elevator_vision.enabled must be true")
            ensure_exists(config.floor.model_path, f"{cfg.camera_id} elevator floor model")
        except (FileNotFoundError, ValueError, KeyError) as exc:
            errors.append(str(exc))

    if errors:
        raise ValueError("Elevator runtime config validation failed:\n- " + "\n- ".join(errors))

def validate_ingest_config(ingest_cfg: IngestConfig) -> None:
    errors = []
    if ingest_cfg.stream_profile not in {"main", "sub", "third"}:
        errors.append("stream_profile must be one of: main, sub, third")
    if ingest_cfg.reader_output_fps <= 0:
        errors.append("reader_output_fps must be > 0")
    if ingest_cfg.buffer_size <= 0:
        errors.append("buffer_size must be > 0")
    if ingest_cfg.reconnect_delay_sec <= 0:
        errors.append("reconnect_delay_sec must be > 0")
    if ingest_cfg.open_timeout_msec <= 0 or ingest_cfg.read_timeout_msec <= 0:
        errors.append("open_timeout_msec/read_timeout_msec must be > 0")
    if ingest_cfg.skip_sleep_ms < 0:
        errors.append("skip_sleep_ms must be >= 0")
    if errors:
        raise ValueError("Ingest config validation failed:\n- " + "\n- ".join(errors))

def validate_gui_config(gui_cfg: dict) -> None:
    errors = []
    for key in ("grid_rows", "grid_cols", "cell_min_width", "cell_min_height", "grid_spacing"):
        if key not in gui_cfg:
            errors.append(f"gui.json missing {key}")
    if errors:
        raise ValueError("GUI config validation failed:\n- " + "\n- ".join(errors))
