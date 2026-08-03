from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from core.path_utils import PROJECT_ROOT, resolve_project_path


ROI = [
    [0.2, 0.30],
    [0.8, 0.30],
    [0.8, 1.00],
    [0.2, 1.00],
]


def elevator_roi_xyxy(frame_shape: tuple[int, int, int]) -> tuple[int, int, int, int]:
    height, width = frame_shape[:2]
    x1 = max(0, min(width - 1, int(round(ROI[0][0] * width))))
    y1 = max(0, min(height - 1, int(round(ROI[0][1] * height))))
    x2 = max(x1 + 1, min(width, int(round(ROI[1][0] * width))))
    y2 = max(y1 + 1, min(height, int(round(ROI[2][1] * height))))
    return x1, y1, x2, y2


def classify_frame(model: YOLO, frame, conf_threshold: float, device: str | int) -> tuple[str, float]:
    x1, y1, x2, y2 = elevator_roi_xyxy(frame.shape)
    crop = frame[y1:y2, x1:x2]
    result = model.predict(crop, conf=conf_threshold, verbose=False, device=device)[0]
    probs = getattr(result, "probs", None)
    if probs is None:
        return "unknown", 0.0

    cls_id = int(probs.top1)
    confidence = float(probs.top1conf)
    names = model.names
    if isinstance(names, dict):
        label = names.get(cls_id, str(cls_id))
    else:
        label = names[cls_id] if 0 <= cls_id < len(names) else str(cls_id)
    return str(label).strip().lower(), confidence


def draw_overlay(frame, label: str, confidence: float, fps: float) -> None:
    x1, y1, x2, y2 = elevator_roi_xyxy(frame.shape)
    color = (0, 200, 0) if label == "empty" else (0, 0, 255) if label == "occupied" else (0, 180, 255)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    text = f"{label.upper()}  {confidence:.3f}  {fps:.1f} FPS"
    cv2.putText(frame, text, (x1, max(30, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)


def resize_for_display(frame, scale: float):
    if scale <= 0 or abs(scale - 1.0) < 1e-6:
        return frame
    h, w = frame.shape[:2]
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quick demo for elevator empty/occupied classification")
    parser.add_argument(
        "--video",
        default="dataTest/videoTest/192.168.11.6_01_20260803133159596.mp4",
        help="Input video path",
    )
    parser.add_argument(
        "--weights",
        default="weights_classification/best.pt",
        help="Classification weights path",
    )
    parser.add_argument("--conf", type=float, default=0.5, help="Confidence threshold")
    parser.add_argument("--device", default=0, help="YOLO device. Use 0 for GPU, 'cpu' for CPU")
    parser.add_argument("--scale", type=float, default=0.75, help="Display scale factor")
    parser.add_argument("--step", type=int, default=1, help="Process every Nth frame")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video_path = resolve_project_path(args.video)
    if not Path(video_path).exists() and "imageTest" in str(args.video):
        alt_video_path = resolve_project_path(str(args.video).replace("imageTest", "videoTest"))
        if Path(alt_video_path).exists():
            video_path = alt_video_path
    weights_path = resolve_project_path(args.weights)

    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not Path(weights_path).exists():
        raise FileNotFoundError(f"Weights not found: {weights_path}")

    model = YOLO(str(weights_path))
    device = args.device
    if str(device).strip() == "0":
        try:
            import torch

            if not torch.cuda.is_available():
                device = "cpu"
        except Exception:
            device = "cpu"
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    frame_idx = 0
    last_time = time.perf_counter()
    window_name = "Elevator Classification Demo"

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame_idx += 1
        if args.step > 1 and (frame_idx % args.step) != 0:
            continue

        label, confidence = classify_frame(model, frame, args.conf, device)
        now = time.perf_counter()
        fps = 1.0 / max(1e-6, now - last_time)
        last_time = now

        draw_overlay(frame, label, confidence, fps)
        frame = resize_for_display(frame, args.scale)

        cv2.imshow(window_name, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
