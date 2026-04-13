import cv2
import numpy as np

from core.types import DetectionResult, ZoneConfig, ZoneState


STATE_COLORS = {
    "occupied": (0, 0, 150),
    "empty": (0, 150, 0),
    "unknown": (0, 150, 150),
}

DET_COLORS = {
    "person": (0, 255, 0),
    "obstacle": (0, 165, 255),
    "pallet": (255, 0, 0),
    "trolley": (255, 255, 0),
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
        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = 0.5

        (tw, th), _ = cv2.getTextSize(label, font, font_scale, 1)
        x, y = points[0]

        cv2.rectangle(canvas, (x, y - th - 6), (x + tw + 4, y), color, -1)

        cv2.putText(canvas, label, (x + 2, y - 2), font, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

    if detection_result is not None:
        for det in detection_result.detections:
            x1, y1, x2, y2 = det.bbox_xyxy
            cls_name = det.class_name
            conf = det.confidence

            color = DET_COLORS.get(cls_name, (180, 180, 180))

            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 1)

            label = f"{cls_name} {conf:.2f}"

            font = cv2.FONT_HERSHEY_DUPLEX
            font_scale = 0.5
            font_thickness = 1

            (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thickness)

            text_y = y1 - 6 if y1 - th - 6 > 0 else y1 + th + 6

            cv2.rectangle(
                canvas,
                (x1, text_y - th - 4),
                (x1 + tw + 4, text_y),
                color,
                -1
            )

            cv2.putText(
                canvas,
                label,
                (x1 + 2, text_y - 2),
                font,
                font_scale,
                (255, 255, 255),
                font_thickness,
                cv2.LINE_AA
            )

    return canvas
