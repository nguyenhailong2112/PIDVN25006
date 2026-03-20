import time

import cv2

from core.config import load_camera_configs, load_rule_config, load_zone_configs
from core.debug_utils import StageTimer
from core.detector import YoloDetector
from core.logger_config import get_logger
from core.path_utils import PROJECT_ROOT, ensure_exists
from core.state_tracker import StateTracker
from core.visualizer import draw_debug_frame
from core.zone_reasoner import ZoneReasoner


CAMERA_CONFIG_PATH = PROJECT_ROOT / "configs" / "cameras.json"
RULE_CONFIG_PATH = PROJECT_ROOT / "configs" / "rules.json"
logger = get_logger(__name__)


def print_state_changes(states):
    for state in states:
        logger.info(
            "[%s] %s: state=%s, score=%.2f, health=%s",
            state.camera_id,
            state.zone_id,
            state.state,
            state.score,
            state.health,
        )


def print_snapshot(states):
    if not states:
        return
    parts = [f"{state.zone_id}={1 if state.state == 'occupied' else 0}" for state in states]
    logger.info(" | ".join(parts))


def main() -> None:
    camera_configs = [cfg for cfg in load_camera_configs(CAMERA_CONFIG_PATH) if cfg.enabled]
    if not camera_configs:
        raise RuntimeError("No enabled camera configuration found.")

    camera_cfg = camera_configs[0]
    rule_cfg = load_rule_config(RULE_CONFIG_PATH)

    zone_config_path = ensure_exists(camera_cfg.zone_config, "Zone config")
    model_path = ensure_exists(camera_cfg.model_path, "Model file")
    source_path = ensure_exists(camera_cfg.source_path, "Replay source")

    zone_configs = load_zone_configs(zone_config_path)
    detector = YoloDetector(
        str(model_path),
        rule_cfg.conf_threshold,
        rule_cfg.img_size,
        rule_cfg.batch_size,
        rule_cfg.batch_timeout_ms,
        rule_cfg.max_pending_requests,
    )
    reasoner = ZoneReasoner(zone_configs, rule_cfg)
    tracker = StateTracker(rule_cfg)

    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source: {source_path}")

    frame_id = 0
    last_detection_result = None
    timer = StageTimer()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_id += 1
        timestamp = time.time()

        if frame_id % camera_cfg.infer_every_n_frames == 0:
            timer.start()
            detection_result = detector.infer(frame, camera_cfg.camera_id, frame_id, timestamp)
            detect_ms = timer.elapsed_ms()

            if detection_result is not None:
                last_detection_result = detection_result
                observations = reasoner.observe(detection_result, frame.shape)
                changed_states = tracker.update_observations(observations)
                if changed_states:
                    print_state_changes(changed_states)

            if frame_id % 30 == 0:
                logger.info("[%s] detect_time_ms=%.1f", camera_cfg.camera_id, detect_ms)

        current_states = tracker.get_current_states(camera_cfg.camera_id, timestamp)

        if frame_id % 30 == 0:
            print_snapshot(current_states)

        debug_frame = draw_debug_frame(frame, last_detection_result, zone_configs, current_states)
        cv2.imshow(f"Replay - {camera_cfg.name}", cv2.resize(debug_frame, (1280, 720)))

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
