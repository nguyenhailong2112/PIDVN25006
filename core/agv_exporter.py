from pathlib import Path

from core.file_utils import write_image_atomic, write_json_atomic


class AgvExporter:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frame_dir = self.output_dir.parent / "agv_frames"
        self.frame_dir.mkdir(parents=True, exist_ok=True)

    def export_snapshot(self, payload: dict) -> Path:
        output_path = self.output_dir / "agv_latest.json"
        return write_json_atomic(output_path, payload)

    def export_camera(self, camera_id: str, payload: dict) -> Path:
        output_path = self.output_dir / f"{camera_id}_latest.json"
        return write_json_atomic(output_path, payload)

    def export_debug_frame(self, camera_id: str, frame_bgr) -> Path | None:
        if frame_bgr is None:
            return None
        output_path = self.frame_dir / f"{camera_id}.jpg"
        return write_image_atomic(output_path, frame_bgr)
