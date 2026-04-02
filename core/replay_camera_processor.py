from pathlib import Path
import time

from core.config import load_zone_configs
from core.detector import YoloDetector
from core.path_utils import ensure_exists
from core.replay_source import ReplaySource
from core.state_tracker import StateTracker
from core.visualizer import draw_debug_frame
from core.zone_reasoner import ZoneReasoner


class ReplayCameraProcessor:
    def __init__(self, project_root, camera_config, rule_config, target_fps: float | None = None) -> None:
        self.project_root = Path(project_root)
        self.camera_config = camera_config
        self.rule_config = rule_config
        self.last_frame_id = -1
        self.last_result = None

        source_path = ensure_exists(camera_config.source_path, "Replay source")
        model_path = ensure_exists(camera_config.model_path, "Model file")

        self.source = ReplaySource(str(source_path), loop=True, target_fps=target_fps)
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

    def step(self):
        ok, frame, frame_id, timestamp = self.source.read()
        if not ok or frame is None:
            return None

        if frame_id == self.last_frame_id and self.last_result is not None:
            return self.last_result

        self.last_frame_id = frame_id
        raw_frame = frame.copy()
        changed_states = []
        current_states = []
        zone_occupancy = []
        detect_ms = 0.0

        fresh_detection_result = None

        if frame_id % self.camera_config.infer_every_n_frames == 0:
            t0 = time.perf_counter()
            detection_result = self.detector.infer(
                frame,
                self.camera_config.camera_id,
                frame_id,
                timestamp,
            )
            if detection_result is not None:
                fresh_detection_result = detection_result
                self.last_detection_result = detection_result
                detect_ms = (time.perf_counter() - t0) * 1000.0

                if self.reasoner is not None and self.tracker is not None:
                    observations = self.reasoner.observe(fresh_detection_result, frame.shape)
                    changed_states = self.tracker.update_observations(observations)

        if self.reasoner is not None and self.tracker is not None:
            current_states = self.tracker.get_current_states(self.camera_config.camera_id, timestamp)
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
            debug_frame = draw_debug_frame(frame, self.last_detection_result, self.zone_configs, current_states)
        else:
            debug_frame = draw_debug_frame(frame, self.last_detection_result, [], [])

        self.last_result = {
            "camera_id": self.camera_config.camera_id,
            "camera_name": self.camera_config.name,
            "camera_type": self.camera_config.camera_type,
            "camera_health": "replay",
            "frame_id": frame_id,
            "timestamp": timestamp,
            "changed_states": changed_states,
            "current_states": current_states,
            "zone_occupancy": zone_occupancy,
            "raw_frame": raw_frame,
            "debug_frame": debug_frame,
            "detect_ms": detect_ms,
        }
        return self.last_result

    def close(self) -> None:
        self.source.release()
