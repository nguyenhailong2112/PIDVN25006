import json
from pathlib import Path

from core.types import ZoneState


class StateExporter:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_camera_snapshot(self, camera_id: str, states: list[ZoneState], timestamp: float) -> Path:
        payload = {
            "camera_id": camera_id,
            "timestamp": timestamp,
            "zones": [
                {
                    "zone_id": state.zone_id,
                    "state": state.state,
                    "score": round(state.score, 4),
                    "health": state.health,
                }
                for state in states
            ],
        }

        output_path = self.output_dir / f"{camera_id}_latest.json"
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path
