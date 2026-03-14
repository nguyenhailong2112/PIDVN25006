from core.config import load_camera_configs, load_rule_config
from core.history_logger import HistoryLogger
from core.path_utils import PROJECT_ROOT
from core.replay_camera_processor import ReplayCameraProcessor

import cv2


CAMERA_CONFIG_PATH = PROJECT_ROOT / "configs" / "cameras.json"
RULE_CONFIG_PATH = PROJECT_ROOT / "configs" / "rules.json"
HISTORY_DIR = PROJECT_ROOT / "outputs" / "history"


def print_state_changes(states):
    for state in states:
        print(
            f"[{state.camera_id}] {state.zone_id}: "
            f"state={state.state}, score={state.score:.2f}, health={state.health}"
        )


def make_grid(frames, cols=2, cell_size=(960, 540)):
    if not frames:
        return None

    resized = [cv2.resize(frame, cell_size) for frame in frames]
    rows = []

    for i in range(0, len(resized), cols):
        row_frames = resized[i:i + cols]
        if len(row_frames) < cols:
            blank = 255 * resized[0].copy()
            while len(row_frames) < cols:
                row_frames.append(blank)
        rows.append(cv2.hconcat(row_frames))

    return cv2.vconcat(rows)


def main() -> None:
    camera_configs = [cfg for cfg in load_camera_configs(CAMERA_CONFIG_PATH) if cfg.enabled]
    if not camera_configs:
        raise RuntimeError("No enabled cameras found.")

    rule_cfg = load_rule_config(RULE_CONFIG_PATH)
    processors = [ReplayCameraProcessor(PROJECT_ROOT, cfg, rule_cfg) for cfg in camera_configs]
    history_logger = HistoryLogger(HISTORY_DIR)

    try:
        while True:
            frames = []

            for processor in processors:
                result = processor.step()
                if result is None:
                    continue

                if result["changed_states"]:
                    print_state_changes(result["changed_states"])
                    history_logger.log_zone_states(
                        result["camera_id"],
                        result["changed_states"],
                        result["timestamp"],
                    )

                frame = result["debug_frame"].copy()
                cv2.putText(
                    frame,
                    result["camera_name"],
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (255, 255, 255),
                    2,
                )
                frames.append(frame)

            if not frames:
                break

            grid = make_grid(frames, cols=2, cell_size=(960, 540))
            cv2.imshow("Multi Camera Replay", grid)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

    finally:
        for processor in processors:
            processor.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
