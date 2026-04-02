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
class IngestConfig:
    stream_profile: str = "main"
    latest_frame_only: bool = True
    reader_output_fps: float = 10.0
    expected_source_fps: float = 25.0
    buffer_size: int = 1
    reconnect_delay_sec: float = 1.0
    rtsp_transport: str = "tcp"
    open_timeout_msec: int = 2000
    read_timeout_msec: int = 1000
    skip_sleep_ms: int = 2

@dataclass
class ZoneConfig:
    zone_id: str
    target_object: str
    polygon: list[tuple[float, float]]
    spatial_method: str | None = None


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
    max_pending_requests: int = 0


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
