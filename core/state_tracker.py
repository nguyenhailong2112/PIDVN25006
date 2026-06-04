from collections import deque

from core.types import RuleConfig, ZoneObservation, ZoneState


class StateTracker:
    def __init__(self, rules: RuleConfig) -> None:
        self.rules = rules
        self.history: dict[str, deque[bool]] = {}
        self.states: dict[str, ZoneState] = {}
        self.last_observation_ts: dict[str, float] = {}
        self.last_present_ts: dict[str, float] = {}
        self.candidate_state: dict[str, str] = {}
        self.candidate_since: dict[str, float] = {}
        self.state_since: dict[str, float] = {}

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
                self.state_since[key] = obs.timestamp

            self.history[key].append(obs.target_present)
            self.last_observation_ts[key] = obs.timestamp
            if obs.target_present:
                self.last_present_ts[key] = obs.timestamp

            new_state = self._decide_state(obs, key)
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

    def _decide_state(self, obs: ZoneObservation, key: str) -> ZoneState:
        history = list(self.history[key])
        prev = self.states[key]
        timestamp = obs.timestamp

        enter_slice = history[-self.rules.enter_window:]
        exit_slice = history[-self.rules.exit_window:]

        present_count = sum(enter_slice)
        absent_count = len(exit_slice) - sum(exit_slice)

        raw_state = None
        raw_score = prev.score

        # Hysteresis avoids state flicker when detections momentarily drop or overlap between slots.
        if present_count >= self.rules.enter_count:
            raw_state = "occupied"
            raw_score = present_count / max(1, len(enter_slice))
        elif absent_count >= self.rules.exit_count:
            raw_state = "empty"
            raw_score = absent_count / max(1, len(exit_slice))

        if prev.state == "occupied" and not obs.target_present and obs.occlusion_present:
            raw_state = None

        if (
            prev.state == "occupied"
            and raw_state == "empty"
            and self.rules.occupied_hold_sec > 0.0
            and key in self.last_present_ts
            and (timestamp - self.last_present_ts[key]) < self.rules.occupied_hold_sec
        ):
            raw_state = None

        state, score, since_ts = self._resolve_stable_state(
            key=key,
            previous=prev,
            raw_state=raw_state,
            raw_score=raw_score,
            timestamp=timestamp,
        )

        return ZoneState(
            camera_id=obs.camera_id,
            zone_id=obs.zone_id,
            state=state,
            score=score,
            timestamp=since_ts,
            health="online",
        )

    def _resolve_stable_state(
        self,
        *,
        key: str,
        previous: ZoneState,
        raw_state: str | None,
        raw_score: float,
        timestamp: float,
    ) -> tuple[str, float, float]:
        if raw_state is None:
            self.candidate_state.pop(key, None)
            self.candidate_since.pop(key, None)
            return previous.state, previous.score, self.state_since.get(key, previous.timestamp)

        if raw_state == previous.state:
            self.candidate_state.pop(key, None)
            self.candidate_since.pop(key, None)
            return previous.state, raw_score, self.state_since.get(key, previous.timestamp)

        if self.candidate_state.get(key) != raw_state:
            self.candidate_state[key] = raw_state
            self.candidate_since[key] = timestamp

        candidate_since = self.candidate_since[key]
        confirm_sec = self.rules.enter_confirm_sec if raw_state == "occupied" else self.rules.exit_confirm_sec
        if (timestamp - candidate_since) < confirm_sec:
            return previous.state, previous.score, self.state_since.get(key, previous.timestamp)

        self.candidate_state.pop(key, None)
        self.candidate_since.pop(key, None)
        self.state_since[key] = candidate_since
        return raw_state, raw_score, candidate_since

    def _apply_unknown_timeout(self, key: str, state: ZoneState, timestamp: float) -> ZoneState:
        last_ts = self.last_observation_ts.get(key)
        # In industrial runtime, stale input must become unknown, never silently become empty.
        if last_ts is None or timestamp - last_ts > self.rules.unknown_timeout_sec:
            unknown_since = last_ts if last_ts is not None else timestamp
            self.state_since[key] = unknown_since
            self.candidate_state.pop(key, None)
            self.candidate_since.pop(key, None)
            return ZoneState(
                camera_id=state.camera_id,
                zone_id=state.zone_id,
                state="unknown",
                score=0.0,
                timestamp=unknown_since,
                health="unknown",
            )
        return state

    @staticmethod
    def _zone_key(camera_id: str, zone_id: str) -> str:
        return f"{camera_id}:{zone_id}"
