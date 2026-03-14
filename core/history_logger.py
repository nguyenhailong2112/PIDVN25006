import json
from pathlib import Path

from core.types import ZoneState


class HistoryLogger:
    """
    Ghi lịch sử thay đổi trạng thái theo từng camera dưới dạng JSONL.
    Mỗi dòng là một bản ghi độc lập, rất tiện để debug hoặc replay lại log.
    """

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log_zone_states(self, camera_id: str, states: list[ZoneState], timestamp: float) -> Path:
        output_path = self.output_dir / f"{camera_id}_history.jsonl"

        with output_path.open("a", encoding="utf-8") as f:
            for state in states:
                record = {
                    "timestamp": timestamp,
                    "camera_id": state.camera_id,
                    "zone_id": state.zone_id,
                    "state": state.state,
                    "score": round(state.score, 4),
                    "health": state.health,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return output_path
