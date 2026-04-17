from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BOOTSTRAP_ROOT = Path(__file__).resolve().parents[1]
if str(BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP_ROOT))

from core.config import load_json_dict
from core.file_utils import write_json_atomic
from core.path_utils import PROJECT_ROOT, resolve_project_path
from core.runtime_bridge import ELEVATOR_COMMANDS_PATH


ELEVATOR_CONFIG_PATH = PROJECT_ROOT / "configs" / "elevator.json"


def _command_path() -> Path:
    try:
        payload = load_json_dict(ELEVATOR_CONFIG_PATH)
    except Exception:
        return ELEVATOR_COMMANDS_PATH
    return resolve_project_path(payload.get("command_path") or ELEVATOR_COMMANDS_PATH)


def _load_existing_sequence(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return 0
    raw_commands = payload.get("commands", payload) if isinstance(payload, dict) else payload
    if isinstance(raw_commands, dict):
        raw_commands = [raw_commands]
    if not isinstance(raw_commands, list):
        return 0
    sequence = 0
    for raw in raw_commands:
        if not isinstance(raw, dict):
            continue
        try:
            sequence = max(sequence, int(raw.get("sequence", 0)))
        except (TypeError, ValueError):
            continue
    return sequence


def _load_existing_commands(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    raw_commands = payload.get("commands", payload) if isinstance(payload, dict) else payload
    if isinstance(raw_commands, dict):
        raw_commands = [raw_commands]
    if not isinstance(raw_commands, list):
        return []
    return [dict(item) for item in raw_commands if isinstance(item, dict)]


def _command_sequence(raw: dict) -> int:
    try:
        return int(raw.get("sequence", 0))
    except (TypeError, ValueError):
        return 0


def _write_command(args) -> None:
    command_path = _command_path()
    sequence = args.sequence if args.sequence is not None else (_load_existing_sequence(command_path) + 1)
    existing = _load_existing_commands(command_path)
    existing = [item for item in existing if _command_sequence(item) < sequence]
    existing.append(
        {
            "sequence": sequence,
            "camera_id": args.camera_id,
            "command": args.command_name,
            "task_id": args.task_id,
            "vehicle_id": args.vehicle_id,
            "expected_load_type": args.expected_load_type,
            "timestamp": time.time(),
        }
    )
    payload = {
        "commands": existing[-200:]
    }
    write_json_atomic(command_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write one elevator workflow command for the backend runtime")
    parser.add_argument("command_name", choices=["authorize", "entry_complete", "release", "continue", "cancel"])
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--vehicle-id", default="")
    parser.add_argument("--expected-load-type", default="")
    parser.add_argument("--sequence", type=int, default=None)
    parser.set_defaults(func=_write_command)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
