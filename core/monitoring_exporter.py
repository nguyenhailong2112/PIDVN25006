import json
from pathlib import Path

from core.types import DetectionResult


class MonitoringExporter:
    """
    Dùng cho camera kiểu general_monitoring như Cam064.
    Ghi detection mới nhất ra file JSON để tiện kiểm tra và tích hợp về sau.
    """

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_detection_snapshot(self, detection_result: DetectionResult) -> Path:
        payload = {
            "camera_id": detection_result.camera_id,
            "frame_id": detection_result.frame_id,
            "timestamp": detection_result.timestamp,
            "detections": [
                {
                    "class_name": det.class_name,
                    "confidence": round(det.confidence, 4),
                    "bbox_xyxy": list(det.bbox_xyxy),
                }
                for det in detection_result.detections
            ],
        }

        output_path = self.output_dir / f"{detection_result.camera_id}_latest_detection.json"
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return output_path
