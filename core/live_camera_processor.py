from pathlib import Path
import time

from core.camera_reader import CameraReader
from core.config import load_zone_configs
from core.detector import YoloDetector
from core.frame_store import FrameStore
from core.monitoring_exporter import MonitoringExporter
from core.path_utils import ensure_exists, resolve_project_path
from core.state_exporter import StateExporter
from core.state_tracker import StateTracker
from core.visualizer import draw_debug_frame
from core.zone_reasoner import ZoneReasoner


class LiveCameraProcessor:
    def __init__(self, project_root, camera_config, rule_config) -> None:
        self.project_root = Path(project_root)
        self.camera_config = camera_config
        self.rule_config = rule_config
        self.last_frame_id = -1
        self.last_result = None

        source_path = self._resolve_source(camera_config.source_type, camera_config.source_path)
        model_path = ensure_exists(camera_config.model_path, "Model file")

        self.frame_store = FrameStore()
        self.reader = CameraReader(camera_config.camera_id, source_path, self.frame_store)
        self.reader.start()

        self.detector = YoloDetector(
            str(model_path),
            rule_config.conf_threshold,
            rule_config.img_size,
            rule_config.batch_size,
            rule_config.batch_timeout_ms,
        )
        self.last_detection_result = None

        self.state_exporter = StateExporter(self.project_root / "outputs" / "multi_runtime")
        self.monitoring_exporter = MonitoringExporter(self.project_root / "outputs" / "monitoring")

        self.zone_configs = []
        self.reasoner = None
        self.tracker = None

        if camera_config.camera_type in ["trolley_slot", "pallet_slot"]:
            zone_config_path = ensure_exists(camera_config.zone_config, "Zone config")
            self.zone_configs = load_zone_configs(zone_config_path)
            self.reasoner = ZoneReasoner(self.zone_configs, rule_config)
            self.tracker = StateTracker(rule_config)

    def _resolve_source(self, source_type: str, source_path: str) -> str:
        if source_type.lower() in {"rtsp", "live"}:
            return source_path
        return str(ensure_exists(resolve_project_path(source_path), "Video source"))

    def step(self):
        live_frame = self.frame_store.get_latest(self.camera_config.camera_id)
        if live_frame is None:
            return None

        if live_frame.frame_id == self.last_frame_id and self.last_result is not None:
            return self.last_result

        self.last_frame_id = live_frame.frame_id
        changed_states = []
        current_states = []
        detect_ms = 0.0

        if live_frame.frame_id % self.camera_config.infer_every_n_frames == 0:
            t0 = time.perf_counter()
            self.last_detection_result = self.detector.infer(
                live_frame.frame,
                self.camera_config.camera_id,
                live_frame.frame_id,
                live_frame.timestamp,
            )
            detect_ms = (time.perf_counter() - t0) * 1000.0

            if self.camera_config.camera_type in ["trolley_slot", "pallet_slot"]:
                observations = self.reasoner.observe(self.last_detection_result, live_frame.frame.shape)
                changed_states = self.tracker.update_observations(observations)
                current_states = self.tracker.get_current_states(self.camera_config.camera_id, live_frame.timestamp)
                self.state_exporter.export_camera_snapshot(self.camera_config.camera_id, current_states, live_frame.timestamp)
            elif self.camera_config.camera_type == "general_monitoring":
                self.monitoring_exporter.export_detection_snapshot(self.last_detection_result)

        if self.camera_config.camera_type in ["trolley_slot", "pallet_slot"]:
            current_states = self.tracker.get_current_states(self.camera_config.camera_id, live_frame.timestamp)
            debug_frame = draw_debug_frame(live_frame.frame, self.last_detection_result, self.zone_configs, current_states)
        else:
            debug_frame = draw_debug_frame(live_frame.frame, self.last_detection_result, [], [])

        detections_payload = []
        if self.last_detection_result is not None:
            detections_payload = [
                {
                    "class_name": det.class_name,
                    "confidence": round(det.confidence, 4),
                    "bbox_xyxy": list(det.bbox_xyxy),
                }
                for det in self.last_detection_result.detections
            ]

        self.last_result = {
            "camera_id": self.camera_config.camera_id,
            "camera_name": self.camera_config.name,
            "camera_type": self.camera_config.camera_type,
            "frame_id": live_frame.frame_id,
            "timestamp": live_frame.timestamp,
            "changed_states": changed_states,
            "current_states": current_states,
            "raw_frame": live_frame.frame,
            "debug_frame": debug_frame,
            "detect_ms": detect_ms,
            "detections": detections_payload,
        }
        return self.last_result

    def close(self) -> None:
        self.reader.stop()
