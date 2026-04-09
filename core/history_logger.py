from pathlib import Path

from core.file_utils import append_jsonl_rotating
from core.types import ZoneState


class HistoryLogger:
    """
    Ghi lich su thay doi trang thai theo tung camera duoi dang JSONL.
    Moi dong la mot ban ghi doc lap, tien cho debug va replay.
    """

    def __init__(self, output_dir: str | Path, *, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 7) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max(0, int(max_bytes))
        self.backup_count = max(0, int(backup_count))

    def log_zone_states(self, camera_id: str, states: list[ZoneState], timestamp: float) -> Path:
        output_path = self.output_dir / f"{camera_id}_history.jsonl"

        for state in states:
            record = {
                "timestamp": timestamp,
                "camera_id": state.camera_id,
                "zone_id": state.zone_id,
                "state": state.state,
                "score": round(state.score, 4),
                "health": state.health,
            }
            append_jsonl_rotating(
                output_path,
                record,
                max_bytes=self.max_bytes,
                backup_count=self.backup_count,
            )

        return output_path
