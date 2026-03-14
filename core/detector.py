import numpy as np

from core.inference_scheduler import SchedulerRegistry
from core.model_registry import ModelRegistry
from core.types import Detection, DetectionResult


class YoloDetector:
    def __init__(
        self,
        model_path: str,
        conf_threshold: float,
        img_size: int | None = None,
        batch_size: int = 1,
        batch_timeout_ms: int = 0,
    ) -> None:
        bundle = ModelRegistry.get(model_path)
        self._model = bundle.model
        self.conf_threshold = conf_threshold
        self.img_size = img_size
        self.batch_size = max(1, int(batch_size))
        self.batch_timeout_ms = max(0, int(batch_timeout_ms))
        self._scheduler = SchedulerRegistry.get(
            self._model,
            self.conf_threshold,
            self.img_size,
            self.batch_size,
            self.batch_timeout_ms,
        )

    def infer(self, frame: np.ndarray, camera_id: str, frame_id: int, timestamp: float) -> DetectionResult:
        result = self._scheduler.submit(frame)
        detections: list[Detection] = []

        for box in result.boxes:
            cls_id = int(box.cls[0])
            class_name = self._model.names[cls_id]
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            detections.append(
                Detection(
                    class_name=class_name,
                    confidence=confidence,
                    bbox_xyxy=(x1, y1, x2, y2),
                )
            )

        return DetectionResult(
            camera_id=camera_id,
            frame_id=frame_id,
            timestamp=timestamp,
            detections=detections,
        )
