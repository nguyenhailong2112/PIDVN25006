from __future__ import annotations

from dataclasses import asdict

from core.elevator_types import (
    ElevatorCommand,
    ElevatorCommandResult,
    ElevatorMachineConfig,
    ElevatorObservation,
    ElevatorSnapshot,
    ElevatorWorkflowToken,
)


SAFE_STATES = {"IDLE_CLEAR", "ENTRY_ARMED", "TASK_ACTIVE", "TASK_RELEASE"}


class ElevatorStateMachine:
    def __init__(self, config: ElevatorMachineConfig) -> None:
        self.config = config
        self.state = "IDLE_BLOCKED"
        self.state_since = 0.0
        self.last_transition_reason = "startup_blocked"
        self.fault_code = ""
        self.token: ElevatorWorkflowToken | None = None
        self.last_observation: ElevatorObservation | None = None
        self.last_command: ElevatorCommand | None = None
        self.last_command_status = ""
        self.last_command_reason = ""
        self.last_processed_sequence = 0
        self._clear_candidate_since: float | None = None
        self._intrusion_clear_since: float | None = None
        self._last_intrusion_reason = ""
        self._seen_valid_observation = False

    def observe(self, observation: ElevatorObservation, now_ts: float) -> None:
        self._ensure_started(now_ts)
        self.last_observation = observation
        self._update_clear_candidate(observation, now_ts)

        if observation.is_valid:
            self._seen_valid_observation = True
            if self.state in {"IDLE_BLOCKED", "IDLE_CLEAR", "ENTRY_ARMED", "TASK_ACTIVE", "TASK_RELEASE"}:
                self.fault_code = ""
        else:
            self._intrusion_clear_since = None

        if not observation.is_valid:
            if not self._seen_valid_observation and self.state == "IDLE_BLOCKED":
                self.fault_code = observation.invalid_reason
                return
            if self.config.fail_safe_on_camera_offline or self.token is not None:
                self._transition(
                    "FAULT_UNKNOWN",
                    "observation_invalid",
                    now_ts,
                    fault_code=observation.invalid_reason,
                )
            else:
                self._transition(
                    "IDLE_BLOCKED",
                    "observation_invalid",
                    now_ts,
                    fault_code=observation.invalid_reason,
                )
            return

        if self.state == "FAULT_UNKNOWN":
            if self.token is not None:
                return
            if self._is_clear_stable(now_ts):
                self._transition("IDLE_CLEAR", "fault_recovered_clear", now_ts, fault_code="")
            elif observation.zone_state == "occupied":
                self._transition("IDLE_BLOCKED", "fault_recovered_blocked", now_ts, fault_code="")
            return

        if self.state == "ENTRY_ARMED" and self.token is not None:
            if (now_ts - self.token.authorized_at) > self.config.entry_arm_timeout_sec:
                self._clear_token()
                self._transition("IDLE_BLOCKED", "entry_arm_timeout", now_ts, fault_code="entry_arm_timeout")
                return

        if self.state in {"TASK_ACTIVE", "INTRUSION_ALARM"} and self.token is not None:
            started_at = self.token.entry_completed_at or self.token.authorized_at
            if (now_ts - started_at) > self.config.task_active_timeout_sec:
                self._transition("FAULT_UNKNOWN", "task_active_timeout", now_ts, fault_code="task_active_timeout")
                return

        if self.state == "TASK_RELEASE" and self.token is not None:
            release_at = self.token.release_at or now_ts
            if (now_ts - release_at) > self.config.release_timeout_sec:
                self._clear_token()
                self._transition("IDLE_BLOCKED", "release_timeout", now_ts, fault_code="release_timeout")
                return

        if self.state == "IDLE_BLOCKED":
            if self._is_clear_stable(now_ts):
                self._transition("IDLE_CLEAR", "clear_stable", now_ts, fault_code="")
            return

        if self.state == "IDLE_CLEAR":
            if observation.zone_state != "empty":
                self._transition("IDLE_BLOCKED", "cabin_not_clear", now_ts, fault_code="")
            return

        if self.state in {"ENTRY_ARMED", "TASK_ACTIVE"}:
            intrusion_reason = self._intrusion_reason(observation)
            if intrusion_reason:
                self._last_intrusion_reason = intrusion_reason
                self._intrusion_clear_since = None
                self._transition("INTRUSION_ALARM", "intrusion_detected", now_ts, fault_code="intrusion_detected")
            return

        if self.state == "INTRUSION_ALARM":
            intrusion_reason = self._intrusion_reason(observation)
            if intrusion_reason:
                self._last_intrusion_reason = intrusion_reason
                self._intrusion_clear_since = None
            elif self._intrusion_clear_since is None:
                self._intrusion_clear_since = now_ts
            return

        if self.state == "TASK_RELEASE" and self._is_clear_stable(now_ts):
            self._clear_token()
            self._transition("IDLE_CLEAR", "release_clear_stable", now_ts, fault_code="")

    def apply_command(self, command: ElevatorCommand, now_ts: float) -> ElevatorCommandResult:
        self._ensure_started(now_ts)
        if command.sequence <= self.last_processed_sequence:
            return ElevatorCommandResult(accepted=False, reason="sequence_already_processed")

        self.last_processed_sequence = command.sequence
        self.last_command = command

        handlers = {
            "authorize": self._cmd_authorize,
            "entry_complete": self._cmd_entry_complete,
            "release": self._cmd_release,
            "continue": self._cmd_continue,
            "cancel": self._cmd_cancel,
        }
        handler = handlers.get(command.command)
        if handler is None:
            result = ElevatorCommandResult(accepted=False, reason="unsupported_command")
        else:
            result = handler(command, now_ts)

        self.last_command_status = "accepted" if result.accepted else "rejected"
        self.last_command_reason = result.reason
        return result

    def build_snapshot(self, now_ts: float) -> dict:
        observation = self.last_observation
        token = self.token
        allowed_classes = sorted(self._allowed_classes())
        snapshot = ElevatorSnapshot(
            camera_id=self.config.camera_id,
            zone_id=self.config.zone_id,
            lift_id=self.config.lift_id,
            workflow_type=self.config.workflow_type,
            lift_state=self.state,
            safety_ok=self.state in SAFE_STATES,
            entry_clear=self.state == "IDLE_CLEAR",
            intrusion_alarm=self.state == "INTRUSION_ALARM",
            fault_active=bool(self.fault_code),
            fault_code=self.fault_code,
            transition_reason=self.last_transition_reason,
            task_id=token.task_id if token is not None else "",
            vehicle_id=token.vehicle_id if token is not None else "",
            expected_load_type=token.expected_load_type if token is not None else "",
            camera_health=observation.camera_health if observation is not None else "unknown",
            zone_state=observation.zone_state if observation is not None else "unknown",
            observed_at=observation.observed_at if observation is not None else 0.0,
            updated_at=now_ts,
            state_age_sec=round(max(0.0, now_ts - self.state_since), 3),
            detected_classes=list(observation.detected_classes) if observation is not None else [],
            allowed_detection_classes=allowed_classes,
            intrusion_reason=self._last_intrusion_reason if self.state == "INTRUSION_ALARM" else "",
            last_command_sequence=self.last_processed_sequence,
            last_command_name=self.last_command.command if self.last_command is not None else "",
            last_command_status=self.last_command_status,
            last_command_reason=self.last_command_reason,
        )
        return asdict(snapshot)

    def _cmd_authorize(self, command: ElevatorCommand, now_ts: float) -> ElevatorCommandResult:
        if self.state != "IDLE_CLEAR":
            return ElevatorCommandResult(accepted=False, reason="state_not_idle_clear")
        if not command.task_id.strip():
            return ElevatorCommandResult(accepted=False, reason="task_id_required")
        if self.last_observation is None or not self.last_observation.is_valid:
            return ElevatorCommandResult(accepted=False, reason="camera_not_ready")
        if self.last_observation.zone_state != "empty":
            return ElevatorCommandResult(accepted=False, reason="cabin_not_clear")

        expected_load_type = command.expected_load_type.strip().lower() or self.config.default_expected_load_type
        if expected_load_type not in self.config.allowed_detection_classes:
            return ElevatorCommandResult(accepted=False, reason="unknown_expected_load_type")
        self.token = ElevatorWorkflowToken(
            task_id=command.task_id.strip(),
            vehicle_id=command.vehicle_id.strip(),
            expected_load_type=expected_load_type,
            authorized_at=now_ts,
        )
        self._intrusion_clear_since = None
        self._last_intrusion_reason = ""
        self._transition("ENTRY_ARMED", "authorize", now_ts, fault_code="")
        return ElevatorCommandResult(accepted=True, reason="authorized")

    def _cmd_entry_complete(self, command: ElevatorCommand, now_ts: float) -> ElevatorCommandResult:
        if self.state != "ENTRY_ARMED":
            return ElevatorCommandResult(accepted=False, reason="state_not_entry_armed")
        if not self._matches_token(command):
            return ElevatorCommandResult(accepted=False, reason="task_mismatch")
        if self.token is None:
            return ElevatorCommandResult(accepted=False, reason="missing_token")

        self.token.entry_completed_at = now_ts
        self._transition("TASK_ACTIVE", "entry_complete", now_ts, fault_code="")
        return ElevatorCommandResult(accepted=True, reason="task_active")

    def _cmd_release(self, command: ElevatorCommand, now_ts: float) -> ElevatorCommandResult:
        if self.state != "TASK_ACTIVE":
            return ElevatorCommandResult(accepted=False, reason="state_not_task_active")
        if not self._matches_token(command):
            return ElevatorCommandResult(accepted=False, reason="task_mismatch")
        if self.token is None:
            return ElevatorCommandResult(accepted=False, reason="missing_token")

        self.token.release_at = now_ts
        self._transition("TASK_RELEASE", "release", now_ts, fault_code="")
        return ElevatorCommandResult(accepted=True, reason="task_release")

    def _cmd_continue(self, command: ElevatorCommand, now_ts: float) -> ElevatorCommandResult:
        if self.state != "INTRUSION_ALARM":
            return ElevatorCommandResult(accepted=False, reason="state_not_intrusion_alarm")
        if not self._matches_token(command):
            return ElevatorCommandResult(accepted=False, reason="task_mismatch")
        if self.last_observation is None or not self.last_observation.is_valid:
            return ElevatorCommandResult(accepted=False, reason="camera_not_ready")
        if self._intrusion_reason(self.last_observation):
            return ElevatorCommandResult(accepted=False, reason="intrusion_still_present")
        if not self._is_intrusion_cleared(now_ts):
            return ElevatorCommandResult(accepted=False, reason="intrusion_hold_incomplete")

        self._last_intrusion_reason = ""
        self._transition("TASK_ACTIVE", "continue", now_ts, fault_code="")
        return ElevatorCommandResult(accepted=True, reason="task_resumed")

    def _cmd_cancel(self, command: ElevatorCommand, now_ts: float) -> ElevatorCommandResult:
        if self.token is not None and not self._matches_token(command, allow_empty_task_id=True):
            return ElevatorCommandResult(accepted=False, reason="task_mismatch")

        self._clear_token()
        self._intrusion_clear_since = None
        self._last_intrusion_reason = ""
        target_state = "IDLE_CLEAR" if self._is_clear_stable(now_ts) else "IDLE_BLOCKED"
        self._transition(target_state, "cancel", now_ts, fault_code="")
        return ElevatorCommandResult(accepted=True, reason="cancelled")

    def _matches_token(self, command: ElevatorCommand, *, allow_empty_task_id: bool = False) -> bool:
        if self.token is None:
            return False
        if not command.task_id and allow_empty_task_id:
            return True
        return bool(command.task_id) and command.task_id.strip() == self.token.task_id

    def _allowed_classes(self) -> tuple[str, ...]:
        load_type = self.config.default_expected_load_type
        if self.token is not None and self.token.expected_load_type:
            load_type = self.token.expected_load_type
        normalized = (load_type or "").strip().lower()
        return self.config.allowed_detection_classes.get(normalized, ())

    def _intrusion_reason(self, observation: ElevatorObservation) -> str:
        if not observation.is_valid or self.token is None:
            return ""

        allowed_classes = set(self._allowed_classes())
        unexpected = sorted(cls for cls in observation.detected_classes if cls not in allowed_classes)
        if unexpected:
            return "unexpected_classes:" + ",".join(unexpected)
        return ""

    def _is_clear_stable(self, now_ts: float) -> bool:
        return self._clear_candidate_since is not None and (now_ts - self._clear_candidate_since) >= self.config.clear_stable_sec

    def _is_intrusion_cleared(self, now_ts: float) -> bool:
        return self._intrusion_clear_since is not None and (now_ts - self._intrusion_clear_since) >= self.config.intrusion_hold_sec

    def _update_clear_candidate(self, observation: ElevatorObservation, now_ts: float) -> None:
        if observation.is_valid and observation.zone_state == "empty":
            if self._clear_candidate_since is None:
                self._clear_candidate_since = now_ts
            return
        self._clear_candidate_since = None

    def _transition(self, new_state: str, reason: str, now_ts: float, *, fault_code: str) -> None:
        if self.state == new_state and self.last_transition_reason == reason and self.fault_code == fault_code:
            return
        self.state = new_state
        self.state_since = now_ts
        self.last_transition_reason = reason
        self.fault_code = fault_code
        if new_state != "INTRUSION_ALARM":
            self._intrusion_clear_since = None
        if new_state != "FAULT_UNKNOWN" and not fault_code:
            self.fault_code = ""

    def _clear_token(self) -> None:
        self.token = None

    def _ensure_started(self, now_ts: float) -> None:
        if self.state_since <= 0.0:
            self.state_since = now_ts
