from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from core.config import load_json_dict
from core.elevator_state_machine import ElevatorStateMachine
from core.elevator_types import ElevatorCommand, ElevatorMachineConfig, ElevatorObservation
from core.file_utils import write_json_atomic
from core.logger_config import get_logger
from core.path_utils import ensure_exists, resolve_project_path
from core.runtime_bridge import (
    ELEVATOR_COMMANDS_PATH,
    ELEVATOR_SNAPSHOT_PATH,
    elevator_camera_path,
)


logger = get_logger(__name__)


class ElevatorRuntime:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = ensure_exists(config_path, "Elevator config")
        config_payload = load_json_dict(self.config_path)
        self.command_path = resolve_project_path(config_payload.get("command_path") or ELEVATOR_COMMANDS_PATH)
        self.machines: dict[str, ElevatorStateMachine] = {}
        self._last_command_mtime_ns: int | None = None
        self._last_command_sequence = 0

        for raw_item in config_payload.get("lifts", []):
            config = self._parse_machine_config(raw_item)
            if not config.enabled:
                continue
            self.machines[config.camera_id] = ElevatorStateMachine(config)

        logger.info("ElevatorRuntime started with %d enabled lifts", len(self.machines))

    def update(self, cameras_payload: list[dict], now_ts: float) -> dict:
        if not self.machines:
            empty_payload = {"timestamp": now_ts, "lift_count": 0, "lifts": []}
            write_json_atomic(ELEVATOR_SNAPSHOT_PATH, empty_payload)
            return empty_payload

        camera_map = {str(item.get("camera_id", "")): item for item in cameras_payload}
        commands_by_camera: dict[str, list[ElevatorCommand]] = defaultdict(list)
        for command in self._load_pending_commands():
            commands_by_camera[command.camera_id].append(command)
        for camera_id in commands_by_camera:
            if camera_id not in self.machines:
                logger.warning("[ELEVATOR] Ignoring command for unknown/disabled camera_id=%s", camera_id)

        lift_snapshots = []
        for camera_id, machine in self.machines.items():
            observation = self._build_observation(machine.config, camera_map.get(camera_id), now_ts)
            prev_state = machine.state
            machine.observe(observation, now_ts)
            self._log_state_change(machine, prev_state, phase="observe")

            for command in sorted(commands_by_camera.get(camera_id, []), key=lambda item: item.sequence):
                prev_state = machine.state
                result = machine.apply_command(command, now_ts)
                logger.info(
                    "[ELEVATOR] lift=%s camera=%s cmd=%s seq=%d accepted=%s reason=%s",
                    machine.config.lift_id,
                    camera_id,
                    command.command,
                    command.sequence,
                    result.accepted,
                    result.reason,
                )
                self._log_state_change(machine, prev_state, phase=f"command:{command.command}")

            snapshot = machine.build_snapshot(now_ts)
            write_json_atomic(elevator_camera_path(camera_id), snapshot)
            lift_snapshots.append(snapshot)

        payload = {
            "timestamp": now_ts,
            "lift_count": len(lift_snapshots),
            "lifts": lift_snapshots,
        }
        write_json_atomic(ELEVATOR_SNAPSHOT_PATH, payload)
        return payload

    @staticmethod
    def _parse_machine_config(raw_item: dict) -> ElevatorMachineConfig:
        allowed_detection_classes = {}
        for load_type, classes in dict(raw_item.get("allowed_detection_classes", {})).items():
            normalized_load = str(load_type).strip().lower()
            normalized_classes = tuple(
                sorted({str(class_name).strip().lower() for class_name in (classes or []) if str(class_name).strip()})
            )
            allowed_detection_classes[normalized_load] = normalized_classes

        camera_id = str(raw_item.get("camera_id", "")).strip()
        zone_id = str(raw_item.get("zone_id", "")).strip()
        lift_id = str(raw_item.get("lift_id", raw_item.get("camera_id", ""))).strip()
        workflow_type = str(raw_item.get("workflow_type", "")).strip()
        default_expected_load_type = str(raw_item.get("default_expected_load_type", "none")).strip().lower()
        if not camera_id:
            raise ValueError("Elevator config missing camera_id")
        if not zone_id:
            raise ValueError(f"Elevator config missing zone_id for camera_id={camera_id}")
        if not lift_id:
            raise ValueError(f"Elevator config missing lift_id for camera_id={camera_id}")
        if default_expected_load_type not in allowed_detection_classes:
            raise ValueError(
                f"Elevator config default_expected_load_type={default_expected_load_type} "
                f"not declared in allowed_detection_classes for camera_id={camera_id}"
            )

        return ElevatorMachineConfig(
            enabled=bool(raw_item.get("enabled", True)),
            camera_id=camera_id,
            zone_id=zone_id,
            lift_id=lift_id,
            workflow_type=workflow_type,
            default_expected_load_type=default_expected_load_type,
            allowed_detection_classes=allowed_detection_classes,
            clear_stable_sec=max(0.1, float(raw_item.get("clear_stable_sec", 1.0))),
            entry_arm_timeout_sec=max(1.0, float(raw_item.get("entry_arm_timeout_sec", 30.0))),
            task_active_timeout_sec=max(1.0, float(raw_item.get("task_active_timeout_sec", 180.0))),
            release_timeout_sec=max(1.0, float(raw_item.get("release_timeout_sec", 45.0))),
            intrusion_hold_sec=max(0.1, float(raw_item.get("intrusion_hold_sec", 1.0))),
            unknown_timeout_sec=max(0.5, float(raw_item.get("unknown_timeout_sec", 2.0))),
            fail_safe_on_camera_offline=bool(raw_item.get("fail_safe_on_camera_offline", True)),
        )

    def _load_pending_commands(self) -> list[ElevatorCommand]:
        if not self.command_path.exists():
            self._last_command_mtime_ns = None
            return []

        try:
            mtime_ns = self.command_path.stat().st_mtime_ns
        except OSError:
            return []
        if self._last_command_mtime_ns == mtime_ns:
            return []
        self._last_command_mtime_ns = mtime_ns

        try:
            payload = json.loads(self.command_path.read_text(encoding="utf-8-sig"))
        except Exception:
            logger.exception("Failed to parse elevator command file: %s", self.command_path)
            return []

        if isinstance(payload, dict):
            raw_commands = payload.get("commands", payload)
        else:
            raw_commands = payload
        if isinstance(raw_commands, dict):
            raw_commands = [raw_commands]
        if not isinstance(raw_commands, list):
            return []

        commands: list[ElevatorCommand] = []
        for raw in raw_commands:
            if not isinstance(raw, dict):
                continue
            try:
                sequence = int(raw.get("sequence", 0))
            except (TypeError, ValueError):
                continue
            if sequence <= self._last_command_sequence:
                continue
            command_name = str(raw.get("command", "")).strip().lower()
            camera_id = str(raw.get("camera_id", "")).strip()
            if not command_name or not camera_id:
                continue
            commands.append(
                ElevatorCommand(
                    sequence=sequence,
                    camera_id=camera_id,
                    command=command_name,
                    timestamp=float(raw.get("timestamp", 0.0) or 0.0),
                    task_id=str(raw.get("task_id", "")).strip(),
                    vehicle_id=str(raw.get("vehicle_id", "")).strip(),
                    expected_load_type=str(raw.get("expected_load_type", "")).strip().lower(),
                )
            )

        if commands:
            self._last_command_sequence = max(item.sequence for item in commands)
        return sorted(commands, key=lambda item: item.sequence)

    @staticmethod
    def _build_observation(config: ElevatorMachineConfig, camera_payload: dict | None, now_ts: float) -> ElevatorObservation:
        invalid_reason = ""
        camera_health = "unknown"
        observed_at = 0.0
        zone_state = "unknown"
        detected_classes: tuple[str, ...] = ()

        if camera_payload is None:
            invalid_reason = "camera_payload_missing"
        else:
            camera_health = str(camera_payload.get("camera_health", "unknown")).strip().lower()
            observed_at = float(camera_payload.get("timestamp", 0.0) or 0.0)
            zone_payload = next(
                (item for item in camera_payload.get("zones", []) if str(item.get("zone_id", "")).strip() == config.zone_id),
                None,
            )
            if zone_payload is None:
                invalid_reason = "zone_missing"
            else:
                zone_state = str(zone_payload.get("state", "unknown")).strip().lower()
                detected_classes = tuple(
                    sorted(
                        {
                            str(class_name).strip().lower()
                            for class_name in zone_payload.get("detected_classes", camera_payload.get("detected_classes", []))
                            if str(class_name).strip()
                        }
                    )
                )
                if zone_state not in {"empty", "occupied"}:
                    invalid_reason = f"zone_{zone_state or 'unknown'}"

            if not invalid_reason and camera_health != "online":
                invalid_reason = f"camera_{camera_health or 'unknown'}"
            if not invalid_reason and (observed_at <= 0.0 or (now_ts - observed_at) > config.unknown_timeout_sec):
                invalid_reason = "stale_frame"

        return ElevatorObservation(
            camera_id=config.camera_id,
            zone_id=config.zone_id,
            zone_state=zone_state,
            camera_health=camera_health,
            observed_at=observed_at,
            is_fresh=not invalid_reason,
            detected_classes=detected_classes,
            invalid_reason=invalid_reason,
        )

    @staticmethod
    def _log_state_change(machine: ElevatorStateMachine, prev_state: str, *, phase: str) -> None:
        if prev_state == machine.state:
            return
        logger.info(
            "[ELEVATOR] lift=%s camera=%s phase=%s %s -> %s reason=%s fault=%s",
            machine.config.lift_id,
            machine.config.camera_id,
            phase,
            prev_state,
            machine.state,
            machine.last_transition_reason,
            machine.fault_code,
        )
