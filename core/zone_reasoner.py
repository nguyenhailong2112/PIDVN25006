from core.geometry import is_bbox_all_corners_in_polygon, is_bbox_center_in_polygon, is_bbox_intersects_polygon
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
                if not self._matches_target_object(zone.target_object, det.class_name):
                    continue

                spatial_method = zone.spatial_method or self.rules.spatial_method
                if self._match_detection_to_zone(det.bbox_xyxy, zone.polygon, frame_width, frame_height, spatial_method):
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
        spatial_method: str,
    ) -> bool:
        if spatial_method == "bbox_center":
            return is_bbox_center_in_polygon(bbox_xyxy, polygon, frame_width, frame_height)

        if spatial_method == "bbox_all_corners":
            return is_bbox_all_corners_in_polygon(bbox_xyxy, polygon, frame_width, frame_height)

        if spatial_method == "bbox_intersects":
            return is_bbox_intersects_polygon(bbox_xyxy, polygon, frame_width, frame_height)

        raise ValueError(f"Unsupported spatial_method: {spatial_method}")

    @staticmethod
    def _matches_target_object(target_object: str, class_name: str) -> bool:
        normalized = (target_object or "").strip().lower()
        if normalized in {"*", "any", "any_object", "all"}:
            return True
        return class_name.strip().lower() == normalized
