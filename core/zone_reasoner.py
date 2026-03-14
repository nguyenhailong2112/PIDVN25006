from core.geometry import is_bbox_all_corners_in_polygon, is_bbox_center_in_polygon
from core.types import DetectionResult, RuleConfig, ZoneConfig, ZoneObservation


class ZoneReasoner:
    def __init__(self, zone_configs: list[ZoneConfig], rules: RuleConfig) -> None:
        self.zone_configs = zone_configs
        self.rules = rules

    def observe(self, detection_result: DetectionResult, frame_shape: tuple[int, int, int]) -> list[ZoneObservation]:
        frame_height, frame_width = frame_shape[:2]
        observations: list[ZoneObservation] = []

        for zone in self.zone_configs:
            matched_confidence = None

            for det in detection_result.detections:
                # A zone only cares about its own target object.
                if det.class_name != zone.target_object:
                    continue

                if self._match_detection_to_zone(det.bbox_xyxy, zone.polygon, frame_width, frame_height):
                    if matched_confidence is None or det.confidence > matched_confidence:
                        matched_confidence = det.confidence

            observations.append(
                ZoneObservation(
                    camera_id=detection_result.camera_id,
                    zone_id=zone.zone_id,
                    frame_id=detection_result.frame_id,
                    timestamp=detection_result.timestamp,
                    target_present=matched_confidence is not None,
                    matched_confidence=matched_confidence,
                )
            )

        return observations

    def _match_detection_to_zone(
        self,
        bbox_xyxy: tuple[int, int, int, int],
        polygon: list[tuple[float, float]],
        frame_width: int,
        frame_height: int,
    ) -> bool:
        if self.rules.spatial_method == "bbox_center":
            return is_bbox_center_in_polygon(bbox_xyxy, polygon, frame_width, frame_height)

        if self.rules.spatial_method == "bbox_all_corners":
            # Industrial occupancy logic:
            # count the slot as occupied only when the full trolley/pallet bbox is inside the ROI.
            return is_bbox_all_corners_in_polygon(bbox_xyxy, polygon, frame_width, frame_height)

        raise ValueError(f"Unsupported spatial_method: {self.rules.spatial_method}")
