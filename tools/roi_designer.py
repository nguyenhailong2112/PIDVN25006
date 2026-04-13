import json
from pathlib import Path

import cv2
import numpy as np

from core.path_utils import PROJECT_ROOT, resolve_project_path


class RectROIDesigner:
    def __init__(self, source_path: str, output_path: str, target_object: str, scale: float = 0.75):
        self.source_path = resolve_project_path(source_path)
        self.output_path = resolve_project_path(output_path)
        self.target_object = target_object
        self.scale = scale

        self.original_image = self._load_source(self.source_path)
        self.original_height, self.original_width = self.original_image.shape[:2]

        self.display_width = int(self.original_width * self.scale)
        self.display_height = int(self.original_height * self.scale)
        self.display_image = cv2.resize(self.original_image, (self.display_width, self.display_height))

        self.window_name = "Rect ROI Designer"
        self.start_point = None
        self.current_rect = None
        self.zones = []

    def _load_source(self, source_path: Path) -> np.ndarray:
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        if source_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]:
            image = cv2.imread(str(source_path))
            if image is None:
                raise RuntimeError(f"Cannot load image: {source_path}")
            return image

        cap = cv2.VideoCapture(str(source_path))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {source_path}")

        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError(f"Cannot read first frame from video: {source_path}")
        return frame

    def _to_normalized(self, x_disp: int, y_disp: int) -> tuple[float, float]:
        x_orig = x_disp / self.scale
        y_orig = y_disp / self.scale
        return x_orig / self.original_width, y_orig / self.original_height

    def _rect_to_polygon(self, p1, p2):
        x1, y1 = p1
        x2, y2 = p2
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        return [
            [round(left, 6), round(top, 6)],
            [round(right, 6), round(top, 6)],
            [round(right, 6), round(bottom, 6)],
            [round(left, 6), round(bottom, 6)],
            [round(left, 6), round(top, 6)],
        ]

    def _polygon_to_display_points(self, polygon):
        points = []
        for x_norm, y_norm in polygon:
            x = int(x_norm * self.original_width * self.scale)
            y = int(y_norm * self.original_height * self.scale)
            points.append([x, y])
        return np.array(points, dtype=np.int32)

    def _mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if self.start_point is None:
                self.start_point = self._to_normalized(x, y)
                self.current_rect = None
                print(f"Start point: ({self.start_point[0]:.6f}, {self.start_point[1]:.6f})")
            else:
                end_point = self._to_normalized(x, y)
                self.current_rect = self._rect_to_polygon(self.start_point, end_point)
                self.start_point = None
                print("Rectangle created. Press Enter to save.")

    def _draw_saved_zones(self, canvas):
        for zone in self.zones:
            pts = self._polygon_to_display_points(zone["polygon"])
            overlay = canvas.copy()
            cv2.fillPoly(overlay, [pts], (0, 180, 0))
            cv2.addWeighted(overlay, 0.15, canvas, 0.85, 0, canvas)
            cv2.polylines(canvas, [pts], True, (0, 180, 0), 2)
            cv2.putText(canvas, zone["zone_id"], tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    def _draw_current_rect(self, canvas):
        if self.current_rect is None:
            return
        pts = self._polygon_to_display_points(self.current_rect)
        cv2.polylines(canvas, [pts], True, (0, 0, 255), 2)

    def _draw_help(self, canvas):
        lines = [
            "Left Click 1 : rectangle start",
            "Left Click 2 : rectangle end",
            "Enter        : save current rectangle",
            "C            : clear current rectangle",
            "R            : remove last saved zone",
            "S            : save JSON",
            "Q            : quit",
        ]
        y = 25
        for line in lines:
            cv2.putText(canvas, line, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            y += 28

    def _save_current_rect(self):
        if self.current_rect is None:
            print("No rectangle to save.")
            return

        zone_id = input("Enter zone id (e.g. A1, B2, C3): ").strip()
        if not zone_id:
            print("Zone id cannot be empty.")
            return

        self.zones.append(
            {
                "zone_id": zone_id,
                "target_object": self.target_object,
                "polygon": self.current_rect,
            }
        )
        self.current_rect = None
        print(f"Saved zone: {zone_id}")

    def _remove_last_zone(self):
        if not self.zones:
            print("No saved zone to remove.")
            return
        removed = self.zones.pop()
        print(f"Removed zone: {removed['zone_id']}")

    def _save_json(self):
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": str(self.source_path),
            "target_object": self.target_object,
            "zones": self.zones,
        }
        self.output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved ROI config to: {self.output_path}")

    def run(self):
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        while True:
            canvas = self.display_image.copy()
            self._draw_saved_zones(canvas)
            self._draw_current_rect(canvas)
            self._draw_help(canvas)
            cv2.imshow(self.window_name, canvas)

            key = cv2.waitKey(20) & 0xFF
            if key == 13:
                self._save_current_rect()
            elif key == ord("c"):
                self.start_point = None
                self.current_rect = None
                print("Cleared current rectangle.")
            elif key == ord("r"):
                self._remove_last_zone()
            elif key == ord("s"):
                self._save_json()
            elif key == ord("q"):
                break

        cv2.destroyAllWindows()


if __name__ == "__main__":
    tool = RectROIDesigner(
        source_path="dataTest/imageTest/Cam10/192.168.11.10_01_20260407140324613.jpg",
        output_path="configs/zones_cam10.json",
        target_object="pallet",
        scale=0.75,
    )
    tool.run()
