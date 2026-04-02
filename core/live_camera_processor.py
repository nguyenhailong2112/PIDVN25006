from pathlib import Path
import time

from core.camera_reader import CameraReader
from core.config import load_zone_configs
from core.detector import YoloDetector
from core.frame_store import FrameStore
from core.path_utils import ensure_exists, resolve_project_path
from core.state_tracker import StateTracker
from core.visualizer import draw_debug_frame
from core.zone_reasoner import ZoneReasoner


class LiveCameraProcessor:
    def __init__(
        self,
        project_root,
        camera_config,
        rule_config,
        expected_fps: float | None = None,
        frame_store: FrameStore | None = None,
        ingest_config=None,
        health_reader=None,
        render_debug: bool = True,
        infer_interval_sec: float = 0.0,
    ) -> None:
        self.project_root = Path(project_root)
        self.camera_config = camera_config
        self.rule_config = rule_config
        self.last_frame_id = -1
        self.last_result = None
        self.camera_health = "unknown"
        self.health_reader = health_reader
        self.render_debug = bool(render_debug)
        self.infer_interval_sec = max(0.0, float(infer_interval_sec))
        self.last_infer_ts = 0.0

        source_path = None
        if frame_store is None:
            source_path = self._resolve_source(camera_config.source_type, camera_config.source_path)
        model_path = ensure_exists(camera_config.model_path, "Model file")

        self.frame_store = frame_store or FrameStore()
        self.reader = None
        self._owns_reader = False
        if frame_store is None:
            self.reader = CameraReader(
                camera_config.camera_id,
                source_path,
                self.frame_store,
                expected_fps=expected_fps,
                ingest_config=ingest_config,
            )
            self.reader.start()
            self._owns_reader = True
            self.health_reader = self.reader

        self.detector = YoloDetector(
            str(model_path),
            rule_config.conf_threshold,
            rule_config.img_size,
            rule_config.batch_size,
            rule_config.batch_timeout_ms,
            rule_config.max_pending_requests,
        )
        self.last_detection_result = None

        self.zone_configs = []
        self.reasoner = None
        self.tracker = None

        if camera_config.zone_config:
            zone_config_path = ensure_exists(camera_config.zone_config, "Zone config")
            self.zone_configs = load_zone_configs(zone_config_path)
            self.reasoner = ZoneReasoner(self.zone_configs, rule_config)
            self.tracker = StateTracker(rule_config)

    def _resolve_source(self, source_type: str, source_path: str) -> str:
        if source_type.lower() in {"rtsp", "live"}:
            return source_path
        return str(ensure_exists(resolve_project_path(source_path), "Video source"))

    def _get_camera_health(self) -> str:
        if self.health_reader is not None:
            try:
                return self.health_reader.get_health()
            except Exception:
                return "unknown"
        return self.camera_health

    def step(self):
        live_frame = self.frame_store.get_latest(self.camera_config.camera_id)
        if live_frame is None:
            return None

        if live_frame.frame_id == self.last_frame_id and self.last_result is not None:
            return self.last_result

        self.last_frame_id = live_frame.frame_id
        changed_states = []
        current_states = []
        zone_occupancy = []
        detect_ms = 0.0

        fresh_detection_result = None

        should_infer = live_frame.frame_id % self.camera_config.infer_every_n_frames == 0
        if should_infer and self.infer_interval_sec > 0.0:
            should_infer = (live_frame.timestamp - self.last_infer_ts) >= self.infer_interval_sec

        if should_infer:
            t0 = time.perf_counter()
            detection_result = self.detector.infer(
                live_frame.frame,
                self.camera_config.camera_id,
                live_frame.frame_id,
                live_frame.timestamp,
            )
            if detection_result is not None:
                self.last_infer_ts = live_frame.timestamp
                fresh_detection_result = detection_result
                self.last_detection_result = detection_result
                detect_ms = (time.perf_counter() - t0) * 1000.0

                if self.reasoner is not None and self.tracker is not None:
                    observations = self.reasoner.observe(fresh_detection_result, live_frame.frame.shape)
                    changed_states = self.tracker.update_observations(observations)

        if self.reasoner is not None and self.tracker is not None:
            current_states = self.tracker.get_current_states(self.camera_config.camera_id, live_frame.timestamp)
            zone_occupancy = [
                {
                    "zone_id": state.zone_id,
                    "occupied": 1 if state.state == "occupied" else 0,
                    "state": state.state,
                    "health": state.health,
                    "score": round(state.score, 4),
                }
                for state in current_states
            ]
            debug_frame = None
            if self.render_debug:
                debug_frame = draw_debug_frame(
                    live_frame.frame,
                    self.last_detection_result,
                    self.zone_configs,
                    current_states,
                )
        else:
            debug_frame = None
            if self.render_debug:
                debug_frame = draw_debug_frame(
                    live_frame.frame,
                    self.last_detection_result,
                    [],
                    [],
                )

        self.last_result = {
            "camera_id": self.camera_config.camera_id,
            "camera_name": self.camera_config.name,
            "camera_type": self.camera_config.camera_type,
            "camera_health": self._get_camera_health(),
            "frame_id": live_frame.frame_id,
            "timestamp": live_frame.timestamp,
            "changed_states": changed_states,
            "current_states": current_states,
            "zone_occupancy": zone_occupancy,
            "raw_frame": live_frame.frame,
            "debug_frame": debug_frame,
            "detect_ms": detect_ms,
        }
        return self.last_result

    def close(self) -> None:
        if self._owns_reader and self.reader is not None:
            self.reader.stop()
