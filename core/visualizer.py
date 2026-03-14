import cv2
import numpy as np

from core.types import DetectionResult, ZoneConfig, ZoneState


STATE_COLORS = {
    "occupied": (0, 0, 180),
    "empty": (0, 180, 0),
    "unknown": (0, 180, 180),
}


def draw_debug_frame(
    frame: np.ndarray,
    detection_result: DetectionResult | None,
    zone_configs: list[ZoneConfig],
    zone_states: list[ZoneState],
) -> np.ndarray:
    canvas = frame.copy()
    frame_height, frame_width = canvas.shape[:2]
    state_map = {state.zone_id: state for state in zone_states}

    for zone in zone_configs:
        state = state_map.get(zone.zone_id)
        state_name = state.state if state else "unknown"
        color = STATE_COLORS[state_name]

        points = np.array(
            [[int(x * frame_width), int(y * frame_height)] for x, y in zone.polygon],
            dtype=np.int32,
        )

        overlay = canvas.copy()
        cv2.fillPoly(overlay, [points], color)
        cv2.addWeighted(overlay, 0.18, canvas, 0.82, 0, canvas)
        cv2.polylines(canvas, [points], True, color, 2)

        label = f"{zone.zone_id}: {state_name}"
        cv2.putText(canvas, label, tuple(points[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    # Luôn vẽ detection để cả camera slot-based lẫn general monitoring đều debug được.
    if detection_result is not None:
        for det in detection_result.detections:
            x1, y1, x2, y2 = det.bbox_xyxy
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 255, 0), 2)
            text = f"{det.class_name} {det.confidence:.2f}"
            cv2.putText(canvas, text, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    return canvas
