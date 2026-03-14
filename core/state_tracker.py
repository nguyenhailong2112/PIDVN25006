from collections import deque

from core.types import RuleConfig, ZoneObservation, ZoneState


class StateTracker:
    def __init__(self, rules: RuleConfig) -> None:
        self.rules = rules
        self.history: dict[str, deque[bool]] = {}
        self.states: dict[str, ZoneState] = {}
        self.last_observation_ts: dict[str, float] = {}

    def update_observations(self, observations: list[ZoneObservation]) -> list[ZoneState]:
        changed_states: list[ZoneState] = []

        for obs in observations:
            key = self._zone_key(obs.camera_id, obs.zone_id)

            if key not in self.history:
                self.history[key] = deque(maxlen=max(self.rules.enter_window, self.rules.exit_window))
                self.states[key] = ZoneState(
                    camera_id=obs.camera_id,
                    zone_id=obs.zone_id,
                    state="unknown",
                    score=0.0,
                    timestamp=obs.timestamp,
                    health="unknown",
                )

            self.history[key].append(obs.target_present)
            self.last_observation_ts[key] = obs.timestamp

            new_state = self._decide_state(key, obs.camera_id, obs.zone_id, obs.timestamp)
            if new_state.state != self.states[key].state or abs(new_state.score - self.states[key].score) > 1e-6:
                self.states[key] = new_state
                changed_states.append(new_state)
            else:
                self.states[key] = new_state

        return changed_states

    def get_current_states(self, camera_id: str, timestamp: float) -> list[ZoneState]:
        current_states: list[ZoneState] = []
        prefix = f"{camera_id}:"
        for key, state in self.states.items():
            if key.startswith(prefix):
                current_states.append(self._apply_unknown_timeout(key, state, timestamp))
        return current_states

    def _decide_state(self, key: str, camera_id: str, zone_id: str, timestamp: float) -> ZoneState:
        history = list(self.history[key])

        enter_slice = history[-self.rules.enter_window:]
        exit_slice = history[-self.rules.exit_window:]

        present_count = sum(enter_slice)
        absent_count = len(exit_slice) - sum(exit_slice)

        prev_state = self.states[key].state
        # Hysteresis avoids state flicker when detections momentarily drop or overlap between slots.
        if present_count >= self.rules.enter_count:
            state = "occupied"
            score = present_count / max(1, len(enter_slice))
        elif absent_count >= self.rules.exit_count:
            state = "empty"
            score = absent_count / max(1, len(exit_slice))
        else:
            state = prev_state
            score = self.states[key].score

        return ZoneState(
            camera_id=camera_id,
            zone_id=zone_id,
            state=state,
            score=score,
            timestamp=timestamp,
            health="online",
        )

    def _apply_unknown_timeout(self, key: str, state: ZoneState, timestamp: float) -> ZoneState:
        last_ts = self.last_observation_ts.get(key)
        # In industrial runtime, stale input must become unknown, never silently become empty.
        if last_ts is None or timestamp - last_ts > self.rules.unknown_timeout_sec:
            return ZoneState(
                camera_id=state.camera_id,
                zone_id=state.zone_id,
                state="unknown",
                score=0.0,
                timestamp=timestamp,
                health="unknown",
            )
        return state

    @staticmethod
    def _zone_key(camera_id: str, zone_id: str) -> str:
        return f"{camera_id}:{zone_id}"
