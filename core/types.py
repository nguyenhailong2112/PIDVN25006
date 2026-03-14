from dataclasses import dataclass
from typing import Optional


@dataclass
class CameraConfig:
    camera_id: str
    camera_type: str
    name: str
    source_type: str
    source_path: str
    model_path: str
    zone_config: str
    infer_every_n_frames: int
    enabled: bool = True


@dataclass
class ZoneConfig:
    zone_id: str
    target_object: str
    polygon: list[tuple[float, float]]


@dataclass
class RuleConfig:
    spatial_method: str
    enter_window: int
    enter_count: int
    exit_window: int
    exit_count: int
    unknown_timeout_sec: float
    conf_threshold: float
    img_size: int | None = None
    batch_size: int = 1
    batch_timeout_ms: int = 0


@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox_xyxy: tuple[int, int, int, int]


@dataclass
class DetectionResult:
    camera_id: str
    frame_id: int
    timestamp: float
    detections: list[Detection]


@dataclass
class ZoneObservation:
    camera_id: str
    zone_id: str
    frame_id: int
    timestamp: float
    target_present: bool
    matched_confidence: Optional[float]


@dataclass
class ZoneState:
    camera_id: str
    zone_id: str
    state: str
    score: float
    timestamp: float
    health: str
