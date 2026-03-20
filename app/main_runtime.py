import time
from pathlib import Path

import cv2

from core.camera_reader import CameraReader
from core.config import load_camera_configs, load_ingest_config, load_rule_config, load_zone_configs, validate_ingest_config
from core.detector import YoloDetector
from core.frame_store import FrameStore
from core.logger_config import get_logger
from core.state_tracker import StateTracker
from core.visualizer import draw_debug_frame
from core.zone_reasoner import ZoneReasoner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAMERA_CONFIG_PATH = PROJECT_ROOT / "configs" / "cameras.json"
RULE_CONFIG_PATH = PROJECT_ROOT / "configs" / "rules.json"
INGEST_CONFIG_PATH = PROJECT_ROOT / "configs" / "ingest.json"
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
    ingest_cfg = load_ingest_config(INGEST_CONFIG_PATH)
    validate_ingest_config(ingest_cfg)

    model_path = PROJECT_ROOT / camera_cfg.model_path
    zone_config_path = PROJECT_ROOT / camera_cfg.zone_config
    source_path = camera_cfg.source_path

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

    frame_store = FrameStore()
    reader = CameraReader(
        camera_cfg.camera_id,
        source_path,
        frame_store,
        expected_fps=min(float(5), float(ingest_cfg.reader_output_fps)),
        ingest_config=ingest_cfg,
    )
    reader.start()

    last_infer_time = 0.0
    infer_interval = max(0.01, 1.0 / max(1.0, float(5)))
    last_processed_frame_id = -1
    last_detection_result = None

    try:
        while True:
            live_frame = frame_store.get_latest(camera_cfg.camera_id)
            now = time.time()

            if live_frame is None:
                blank = 255 * cv2.imread(str(PROJECT_ROOT / "out.jpg"))
                cv2.putText(blank, "Waiting for camera frame...", (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                cv2.imshow(f"Runtime - {camera_cfg.name}", cv2.resize(blank, (1280, 720)))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            if now - live_frame.timestamp > rule_cfg.unknown_timeout_sec:
                current_states = tracker.get_current_states(camera_cfg.camera_id, now)
                debug_frame = draw_debug_frame(live_frame.frame, last_detection_result, zone_configs, current_states)
                cv2.imshow(f"Runtime - {camera_cfg.name}", cv2.resize(debug_frame, (1280, 720)))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            if live_frame.frame_id != last_processed_frame_id and (now - last_infer_time) >= infer_interval:
                last_processed_frame_id = live_frame.frame_id
                last_infer_time = now

                detection_result = detector.infer(
                    live_frame.frame,
                    camera_cfg.camera_id,
                    live_frame.frame_id,
                    live_frame.timestamp,
                )
                if detection_result is not None:
                    last_detection_result = detection_result
                    observations = reasoner.observe(last_detection_result, live_frame.frame.shape)
                    changed_states = tracker.update_observations(observations)
                    if changed_states:
                        print_state_changes(changed_states)

            current_states = tracker.get_current_states(camera_cfg.camera_id, now)
            debug_frame = draw_debug_frame(live_frame.frame, last_detection_result, zone_configs, current_states)
            cv2.imshow(f"Runtime - {camera_cfg.name}", cv2.resize(debug_frame, (1280, 720)))

            if live_frame.frame_id % 60 == 0:
                print_snapshot(current_states)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        reader.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
