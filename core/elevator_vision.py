from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.path_utils import resolve_project_path
from core.types import Detection, DetectionResult, ElevatorClassifierConfig, ElevatorVisionConfig


if TYPE_CHECKING:
    from core.model_registry import ModelBundle


logger = logging.getLogger(__name__)


@dataclass
class ElevatorDecision:
    state: str
    floor_state: str
    gate_state: str
    confidence: float


class ElevatorVisionProcessor:
    def __init__(self, config: ElevatorVisionConfig) -> None:
        self.config = config
        self._gate_model_missing_logged = False
        self.floor_labels = set(config.floor.labels)
        self.gate_labels = set(config.gate.labels)
        self.prefixed_gate_labels = {f"gate:{label}" for label in self.gate_labels}

    @staticmethod
    def roi_xyxy(frame_shape, roi: list[tuple[float, float]]) -> tuple[int, int, int, int]:
        height, width = frame_shape[:2]
        x1 = max(0, min(width - 1, int(round(roi[0][0] * width))))
        y1 = max(0, min(height - 1, int(round(roi[0][1] * height))))
        x2 = max(x1 + 1, min(width, int(round(roi[1][0] * width))))
        y2 = max(y1 + 1, min(height, int(round(roi[2][1] * height))))
        return x1, y1, x2, y2

    @property
    def floor_model_path(self) -> str:
        return str(resolve_project_path(self.config.floor.model_path))

    @property
    def gate_model_path(self) -> str:
        return str(resolve_project_path(self.config.gate.model_path))

    @property
    def img_size(self) -> int:
        return int(self.config.img_size)

    def floor_crop(self, frame):
        x1, y1, x2, y2 = self.roi_xyxy(frame.shape, self.config.floor.roi)
        return frame[y1:y2, x1:x2]

    def gate_crop(self, frame):
        x1, y1, x2, y2 = self.roi_xyxy(frame.shape, self.config.gate.roi)
        return frame[y1:y2, x1:x2]

    def floor_bbox(self, frame_shape) -> tuple[int, int, int, int]:
        return self.roi_xyxy(frame_shape, self.config.floor.roi)

    def gate_bbox(self, frame_shape) -> tuple[int, int, int, int]:
        return self.roi_xyxy(frame_shape, self.config.gate.roi)

    def gate_model_exists(self) -> bool:
        exists = Path(self.gate_model_path).exists()
        if not exists and not self._gate_model_missing_logged:
            logger.warning("Elevator gate model not found: %s. Elevator gate state will be unknown.", self.gate_model_path)
            self._gate_model_missing_logged = True
        return exists

    def result_to_detection(
        self,
        result,
        bundle: ModelBundle,
        classifier: ElevatorClassifierConfig,
        bbox_xyxy: tuple[int, int, int, int],
        *,
        class_prefix: str = "",
    ) -> Detection | None:
        label, confidence = self.classification_result(result, bundle)
        if not label:
            return None
        if label not in self._labels_for(classifier):
            return None
        return Detection(
            class_name=f"{class_prefix}{label}",
            confidence=confidence,
            bbox_xyxy=bbox_xyxy,
        )

    def _labels_for(self, classifier: ElevatorClassifierConfig) -> set[str]:
        if classifier.name == "floor":
            return self.floor_labels
        if classifier.name == "gate":
            return self.gate_labels
        return set(classifier.labels)

    @staticmethod
    def classification_result(result, bundle: ModelBundle) -> tuple[str, float]:
        probs = getattr(result, "probs", None)
        if probs is None:
            return "", 0.0
        cls_id = int(probs.top1)
        confidence = float(probs.top1conf)
        names = bundle.model.names
        if isinstance(names, dict):
            class_name = names.get(cls_id, cls_id)
        else:
            class_name = names[cls_id] if 0 <= cls_id < len(names) else cls_id
        return str(class_name).strip().lower(), confidence

    def decide(self, detection_result: DetectionResult, conf_threshold: float) -> ElevatorDecision:
        floor_state, floor_conf = self._top_classification(detection_result, self.floor_labels)
        gate_state, gate_conf = self._top_classification(detection_result, self.prefixed_gate_labels)
        if gate_state.startswith("gate:"):
            gate_state = gate_state.split(":", 1)[1]
        if (
            floor_state not in self.floor_labels
            or gate_state not in self.gate_labels
            or floor_conf < conf_threshold
            or gate_conf < conf_threshold
        ):
            return ElevatorDecision(state="unknown", floor_state=floor_state or "unknown", gate_state=gate_state or "unknown", confidence=0.0)
        if floor_state == "empty" and gate_state == "ok":
            return ElevatorDecision(state="empty", floor_state=floor_state, gate_state=gate_state, confidence=min(floor_conf, gate_conf))
        return ElevatorDecision(state="occupied", floor_state=floor_state, gate_state=gate_state, confidence=min(floor_conf, gate_conf))

    @staticmethod
    def _top_classification(detection_result: DetectionResult, allowed_labels: set[str]) -> tuple[str, float]:
        candidates = [
            det for det in detection_result.detections
            if det.class_name.strip().lower() in allowed_labels
        ]
        if not candidates:
            return "", 0.0
        top = max(candidates, key=lambda det: det.confidence)
        return top.class_name.strip().lower(), top.confidence
