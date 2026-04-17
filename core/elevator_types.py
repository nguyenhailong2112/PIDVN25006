from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ElevatorStateName = Literal[
    "IDLE_BLOCKED",
    "IDLE_CLEAR",
    "ENTRY_ARMED",
    "TASK_ACTIVE",
    "INTRUSION_ALARM",
    "TASK_RELEASE",
    "FAULT_UNKNOWN",
]

ElevatorCommandName = Literal["authorize", "entry_complete", "release", "continue", "cancel"]


@dataclass
class ElevatorMachineConfig:
    enabled: bool
    camera_id: str
    zone_id: str
    lift_id: str
    workflow_type: str
    default_expected_load_type: str
    allowed_detection_classes: dict[str, tuple[str, ...]]
    clear_stable_sec: float
    entry_arm_timeout_sec: float
    task_active_timeout_sec: float
    release_timeout_sec: float
    intrusion_hold_sec: float
    unknown_timeout_sec: float
    fail_safe_on_camera_offline: bool = True


@dataclass
class ElevatorObservation:
    camera_id: str
    zone_id: str
    zone_state: str
    camera_health: str
    observed_at: float
    is_fresh: bool
    detected_classes: tuple[str, ...] = ()
    invalid_reason: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.invalid_reason


@dataclass
class ElevatorWorkflowToken:
    task_id: str
    vehicle_id: str
    expected_load_type: str
    authorized_at: float
    entry_completed_at: float | None = None
    release_at: float | None = None


@dataclass(frozen=True)
class ElevatorCommand:
    sequence: int
    camera_id: str
    command: str
    timestamp: float
    task_id: str = ""
    vehicle_id: str = ""
    expected_load_type: str = ""


@dataclass(frozen=True)
class ElevatorCommandResult:
    accepted: bool
    reason: str


@dataclass
class ElevatorSnapshot:
    camera_id: str
    zone_id: str
    lift_id: str
    workflow_type: str
    lift_state: str
    safety_ok: bool
    entry_clear: bool
    intrusion_alarm: bool
    fault_active: bool
    fault_code: str
    transition_reason: str
    task_id: str
    vehicle_id: str
    expected_load_type: str
    camera_health: str
    zone_state: str
    observed_at: float
    updated_at: float
    state_age_sec: float
    detected_classes: list[str] = field(default_factory=list)
    allowed_detection_classes: list[str] = field(default_factory=list)
    intrusion_reason: str = ""
    last_command_sequence: int = 0
    last_command_name: str = ""
    last_command_status: str = ""
    last_command_reason: str = ""
