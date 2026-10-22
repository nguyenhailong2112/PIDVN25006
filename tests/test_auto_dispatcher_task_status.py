"""Regression tests for auto dispatch task tracking (RCS-2000 queryTaskStatus handling).

Covers the 20/10 incident: RCS canceled task QUANGPROPKDD4FGAA420261020164145
(taskStatus "5") and the AMR lane waited on it forever, so auto never created a new task.

Run from the project root with the project environment:
    python -m unittest tests.test_auto_dispatcher_task_status -v

No network: every RCS call goes to a scripted fake. All files go to a temp folder.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from urllib import request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ["PIDVN_LOG_DIR"] = tempfile.mkdtemp(prefix="pidvn_test_logs_")  # keep test logs out of app.log
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auto_dispatcher import AutoDispatchControlServer, AutoDispatcher  # noqa: E402

PK_CD_SOURCES = ["PK_CC3", "PK_CC2", "PK_CC1", "PK_DD4", "PK_DD3", "PK_DD2", "PK_DD1"]
STUCK_TASK = "QUANGPROPKDD4FGAA420261020164145"
# Trimmed copy of outputs/runtime/auto_dispatch_amr/state.json taken on site at 21/10 02:29.
INCIDENT_STATE = {
    "status": "manual_mode",
    "updated_at": 1792524599.208,
    "active_task": {
        "profile_id": "PK_CD",
        "task_code": STUCK_TASK,
        "source": "PK_DD4",
        "dest": "FG_AA4",
        "created_at": 1792489305.814,
        "last_query_at": 1792524595.947,
        "status": "5",
    },
}
T0 = 1792560000.0  # 21/10 12:20 local time, after the incident


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_amr_config() -> dict:
    """Same merge as mainProcess: common auto_dispatch.json + lane file, API server off."""
    common = json.loads((PROJECT_ROOT / "configs" / "auto_dispatch.json").read_text(encoding="utf-8-sig"))
    lane = json.loads((PROJECT_ROOT / "configs" / "auto_dispatch_amr.json").read_text(encoding="utf-8-sig"))
    config = _deep_merge(common, lane)
    config["api_server"] = {"enabled": False}
    return config


class FakeRcs:
    """Scripted RCS. queryTaskStatus answers with task_status[taskCode]; None means RCS does not know it."""

    def __init__(self) -> None:
        self.task_status: dict[str, str | None] = {}
        self.query_override: dict | None = None
        self.created: list[dict] = []
        self.query_req_codes: list[str | None] = []

    def call_rpc(self, api_name: str, payload: dict, req_code: str | None = None) -> dict:
        if api_name == "genAgvSchedulingTask":
            self.created.append(dict(payload))
            self.task_status.setdefault(payload["taskCode"], "1")
            return {"code": "0", "message": "successful", "reqCode": req_code or "", "data": payload["taskCode"]}
        if api_name == "queryTaskStatus":
            if req_code is not None and req_code in self.query_req_codes:
                # Real RCS on site (22/10): a reused reqCode is refused.
                self.query_req_codes.append(req_code)
                return {"code": "1", "message": f"The request number has already existed:{req_code}", "data": ""}
            self.query_req_codes.append(req_code)
            if self.query_override is not None:
                return dict(self.query_override)
            task_code = payload["taskCodes"][0]
            status = self.task_status.get(task_code)
            data = [] if status is None else [
                {"taskCode": task_code, "taskStatus": status, "agvCode": "16675", "taskTyp": "QUANGPRO"}
            ]
            return {"code": "0", "message": "successful", "reqCode": "", "data": data}
        raise AssertionError(f"unexpected RCS call {api_name}")


def cameras_payload(config: dict, occupied: set[str]) -> list[dict]:
    by_camera: dict[str, list[dict]] = {}
    for position, pos_cfg in config["positions"].items():
        by_camera.setdefault(pos_cfg["camera_id"], []).append(
            {"zone_id": pos_cfg["zone_id"], "health": "online", "state": "occupied" if position in occupied else "empty"}
        )
    return [{"camera_id": camera_id, "camera_health": "online", "zones": zones} for camera_id, zones in by_camera.items()]


def bridge_state(config: dict, occupied: set[str]) -> dict:
    zones = {}
    for position, pos_cfg in config["positions"].items():
        is_occupied = position in occupied
        zones[f"{pos_cfg['camera_id']}:{pos_cfg['zone_id']}:bindCtnrAndBin"] = {
            "last_seen_state": "occupied" if is_occupied else "empty",
            "last_bound_ctnr_code": position if is_occupied else "",
            "hybrid_session": {
                "policy": "hybrid_canonical",
                "needs_reconcile": False,
                "actual_ctnr_code": position if is_occupied else "",
            },
        }
    return {"zones": zones}


class DispatcherTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="pidvn_dispatch_test_")
        self.root = Path(self._tmp.name)
        self.fake = FakeRcs()
        self.config = load_amr_config()
        self.occupied = set(PK_CD_SOURCES)
        self.dispatcher: AutoDispatcher | None = None

    def tearDown(self) -> None:
        if self.dispatcher is not None:
            self.dispatcher.close()
        self._tmp.cleanup()

    def make_dispatcher(self, *, state: dict | None = None, mode: str = "auto", profile: str = "PK_CD", **overrides) -> AutoDispatcher:
        config = dict(self.config)
        config.update(overrides)
        runtime_dir = self.root / config["runtime_dir"]
        runtime_dir.mkdir(parents=True, exist_ok=True)
        if state is not None:
            (runtime_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        control = {"operation_mode": mode, "profile_id": profile, "updated_at": T0, "updated_by": "test", "note": ""}
        (self.root / config["control_state_path"]).write_text(json.dumps(control), encoding="utf-8")
        hik_config = {"host": "127.0.0.1", "rpc_port": 9, "callback_server": {"enabled": True}}
        dispatcher = AutoDispatcher(config, hik_config, self.root)
        dispatcher.client.call_rpc = self.fake.call_rpc  # never reach a real RCS
        self.dispatcher = dispatcher
        return dispatcher

    def sync(self, now_ts: float) -> dict:
        self.dispatcher.sync(cameras_payload(self.config, self.occupied), bridge_state(self.config, self.occupied), now_ts=now_ts)
        return self.dispatcher.state

    def events(self) -> list[dict]:
        path = self.root / self.config["runtime_dir"] / "events.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def start_first_task(self, now_ts: float = T0) -> str:
        state = self.sync(now_ts)
        self.assertIn("active_task", state, state.get("status"))
        return state["active_task"]["task_code"]


class IncidentReplayTests(DispatcherTestCase):
    def test_config_maps_rcs_canceled_status_to_failed(self) -> None:
        dispatcher = self.make_dispatcher()
        self.assertEqual(dispatcher._classify_task_status("5"), "failed")
        self.assertEqual(dispatcher._classify_task_status("9"), "completed")
        for status in ("0", "4", "10"):
            self.assertEqual(dispatcher._classify_task_status(status), "abnormal", status)
        for status in ("1", "2", "3", "6"):
            self.assertEqual(dispatcher._classify_task_status(status), "running", status)

    def test_terminal_codes_hold_even_if_config_omits_them(self) -> None:
        dispatcher = self.make_dispatcher(completed_statuses=["completed"], failed_statuses=["failed"])
        self.assertEqual(dispatcher._classify_task_status("5"), "failed")
        self.assertEqual(dispatcher._classify_task_status("9"), "completed")

    def test_stuck_task_is_released_while_in_manual_then_auto_dispatches(self) -> None:
        self.fake.task_status[STUCK_TASK] = "5"
        self.make_dispatcher(state=INCIDENT_STATE, mode="manual", profile="PK_AB")

        state = self.sync(T0)
        self.assertNotIn("active_task", state)
        self.assertEqual(state["status"], "manual_mode")
        self.assertEqual(state["last_failed_task"]["task_code"], STUCK_TASK)
        self.assertEqual(state["last_failed_task"]["failure_reason"], "rcs_task_failed")
        self.assertEqual(state["last_failed_task"]["status_label"], "canceled")

        # Operator presses Auto PK_CD like at 21/10 01:53:11; all 7 PK_CD slots are full.
        result = self.dispatcher.set_control({"operation_mode": "auto", "profile_id": "PK_CD"}, now_ts=T0 + 10)
        self.assertTrue(result["accepted"])
        state = self.sync(T0 + 11)
        self.assertTrue(state["status"].startswith("task_created:QUANGPROPKCC3"), state["status"])
        self.assertEqual(len(self.fake.created), 1)
        self.assertEqual(self.fake.created[0]["userCallCodePath"], ["33${06}", "2${02}"])

    def test_stuck_task_in_auto_is_released_and_auto_stops_until_operator(self) -> None:
        self.fake.task_status[STUCK_TASK] = "5"
        self.make_dispatcher(state=INCIDENT_STATE, mode="auto", profile="PK_CD")

        state = self.sync(T0)
        self.assertEqual(state["status"], f"stopped_task_canceled:{STUCK_TASK}")
        self.assertNotIn("active_task", state)
        for offset in (1, 61, 3600):
            state = self.sync(T0 + offset)
            self.assertEqual(state["status"], f"stopped_task_canceled:{STUCK_TASK}")
        self.assertEqual(self.fake.created, [])
        self.assertIn("task_failed", [event["event"] for event in self.events()])

        self.dispatcher.set_control({"operation_mode": "auto", "profile_id": "PK_CD"}, now_ts=T0 + 3700)
        state = self.sync(T0 + 3701)
        self.assertTrue(state["status"].startswith("task_created:"), state["status"])
        self.assertEqual(len(self.fake.created), 1)

    def test_cancel_on_pda_mid_batch_stops_auto(self) -> None:
        """Site test 22/10: canceling a task on the PDA must not let auto send the next pallet."""
        self.make_dispatcher()
        first = self.start_first_task()
        self.fake.task_status[first] = "5"
        state = self.sync(T0 + 6)
        self.assertEqual(state["status"], f"stopped_task_canceled:{first}")
        self.assertNotIn("batch", state)
        for offset in (66, 120, 1800):
            state = self.sync(T0 + offset)
        self.assertEqual(len(self.fake.created), 1)

        # Auto again: conditions are checked from scratch. PK is no longer full -> wait.
        self.occupied.discard("PK_CC3")
        self.dispatcher.set_control({"operation_mode": "auto", "profile_id": "PK_CD"}, now_ts=T0 + 1900)
        state = self.sync(T0 + 1901)
        self.assertEqual(state["status"], "waiting_pk_full:PK_CD:6/7")
        self.occupied.add("PK_CC3")
        state = self.sync(T0 + 1902)
        self.assertTrue(state["status"].startswith("task_created:QUANGPROPKCC3"), state["status"])

    def test_each_status_query_uses_a_new_req_code(self) -> None:
        self.make_dispatcher()
        task_code = self.start_first_task()
        self.fake.task_status[task_code] = "2"
        self.sync(T0 + 1)
        # setMode forces an immediate re-query; RCS must not refuse it as a duplicate.
        self.dispatcher.set_control({"operation_mode": "auto", "profile_id": "PK_CD"}, now_ts=T0 + 2)
        state = self.sync(T0 + 3)
        self.assertEqual(len(self.fake.query_req_codes), len(set(self.fake.query_req_codes)))
        self.assertNotEqual(state.get("active_task", {}).get("status"), "query_rejected")


class TaskWatchdogTests(DispatcherTestCase):
    def test_completed_task_continues_batch(self) -> None:
        self.make_dispatcher()
        first = self.start_first_task()
        self.fake.task_status[first] = "9"
        state = self.sync(T0 + 6)
        self.assertEqual(state["status"], f"task_completed:{first}")
        state = self.sync(T0 + 7)
        self.assertTrue(state["status"].startswith("task_created:QUANGPROPKCC2"), state["status"])

    def test_running_task_is_never_released_only_flagged_overdue(self) -> None:
        self.make_dispatcher()
        task_code = self.start_first_task()
        self.fake.task_status[task_code] = "2"
        state = self.sync(T0 + 6)
        self.assertEqual(state["status"], f"waiting_task:{task_code}:2")
        state = self.sync(T0 + 6.5)  # between queries the status keeps the RCS code
        self.assertEqual(state["status"], f"waiting_task:{task_code}:2")
        state = self.sync(T0 + 3601)
        self.assertEqual(state["status"], f"task_overdue:{task_code}:2")
        state = self.sync(T0 + 50000)
        self.assertEqual(state["active_task"]["task_code"], task_code)
        self.assertEqual(len(self.fake.created), 1)
        self.assertIn("task_overdue", [event["event"] for event in self.events()])

    def test_abnormal_status_is_released_after_grace(self) -> None:
        self.make_dispatcher()
        task_code = self.start_first_task()
        self.fake.task_status[task_code] = "0"  # sending exception
        state = self.sync(T0 + 6)
        self.assertEqual(state["status"], f"task_abnormal:{task_code}:0")
        state = self.sync(T0 + 300)
        self.assertIn("active_task", state)
        state = self.sync(T0 + 306)
        self.assertNotIn("active_task", state)
        self.assertEqual(state["last_failed_task"]["failure_reason"], "abnormal_status_timeout")

    def test_abnormal_timer_restarts_when_rcs_recovers(self) -> None:
        self.make_dispatcher()
        task_code = self.start_first_task()
        self.fake.task_status[task_code] = "0"
        self.sync(T0 + 6)
        self.fake.task_status[task_code] = "6"  # resending
        self.sync(T0 + 200)
        self.fake.task_status[task_code] = "0"
        self.sync(T0 + 250)
        state = self.sync(T0 + 500)  # 250 s since the second abnormal reading
        self.assertIn("active_task", state)
        state = self.sync(T0 + 551)
        self.assertNotIn("active_task", state)

    def test_task_missing_from_rcs_is_released_after_grace(self) -> None:
        self.make_dispatcher()
        task_code = self.start_first_task()
        self.fake.task_status[task_code] = None
        state = self.sync(T0 + 6)
        self.assertEqual(state["status"], f"task_abnormal:{task_code}:missing")
        state = self.sync(T0 + 307)
        self.assertNotIn("active_task", state)

    def test_rcs_unreachable_keeps_waiting(self) -> None:
        self.make_dispatcher()
        task_code = self.start_first_task()
        self.fake.task_status[task_code] = "2"
        self.sync(T0 + 6)
        self.fake.query_override = {"code": "HTTP_ERROR", "message": "timed out"}
        for offset in (12, 400, 5000, 20000):
            state = self.sync(T0 + offset)
            self.assertEqual(state["status"], f"task_query_error:{task_code}")
            self.assertEqual(state["active_task"]["status"], "2")
        self.assertEqual(len(self.fake.created), 1)

    def test_answer_for_another_task_is_not_taken_as_ours(self) -> None:
        self.make_dispatcher()
        task_code = self.start_first_task()
        self.fake.query_override = {
            "code": "0",
            "message": "successful",
            "data": [{"taskCode": "OTHER_TASK", "taskStatus": "9"}],
        }
        state = self.sync(T0 + 6)
        self.assertEqual(state["active_task"]["task_code"], task_code)
        self.assertEqual(state["status"], f"task_abnormal:{task_code}:missing")

    def test_consecutive_failures_halt_until_next_set_mode(self) -> None:
        """Optional mode stop_auto_on_task_failure=false: skip failed pallets, stop after 3 in a row."""
        self.make_dispatcher(stop_auto_on_task_failure=False)
        now = T0
        for _ in range(3):
            task_code = self.start_first_task(now)
            self.fake.task_status[task_code] = "5"
            self.sync(now + 6)
            now += 100  # past the 60 s cooldown
        state = self.sync(now)
        self.assertEqual(state["status"], "halted_task_failures:PK_CD:3")
        self.assertNotIn("batch", state)
        self.assertEqual(len(self.fake.created), 3)

        self.dispatcher.set_control({"operation_mode": "auto", "profile_id": "PK_CD"}, now_ts=now + 1)
        state = self.sync(now + 2)
        self.assertTrue(state["status"].startswith("task_created:"), state["status"])
        self.assertEqual(len(self.fake.created), 4)


class ClearActiveTaskApiTests(DispatcherTestCase):
    def test_clear_requires_matching_task_code(self) -> None:
        self.fake.task_status[STUCK_TASK] = "2"
        dispatcher = self.make_dispatcher(state=INCIDENT_STATE, mode="manual")
        result = dispatcher.clear_active_task({"taskCode": "WRONG"}, now_ts=T0)
        self.assertFalse(result["accepted"])
        self.assertIn("active_task", dispatcher.state)

        result = dispatcher.clear_active_task({"taskCode": STUCK_TASK, "updated_by": "pda", "note": "AGV idle"}, now_ts=T0)
        self.assertTrue(result["accepted"])
        self.assertNotIn("active_task", dispatcher.state)
        self.assertEqual(dispatcher.state["last_failed_task"]["failure_reason"], "cleared_by_operator")
        self.assertFalse(dispatcher.clear_active_task({"taskCode": STUCK_TASK}, now_ts=T0 + 1)["accepted"])

    def test_clear_over_http_route(self) -> None:
        self.fake.task_status[STUCK_TASK] = "2"
        dispatcher = self.make_dispatcher(state=INCIDENT_STATE, mode="manual")
        server = AutoDispatchControlServer(
            {"host": "127.0.0.1", "port": 0, "base_path": "/service/rest/visionAutoDispatch", "allowlist": []},
            dispatcher,
        )
        server.start()
        try:
            port = server._server.server_address[1]
            body = json.dumps({"reqCode": "REQ_CLEAR_001", "taskCode": STUCK_TASK}).encode("utf-8")
            req = request.Request(
                f"http://127.0.0.1:{port}/service/rest/visionAutoDispatch/amr/clearActiveTask",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=5) as resp:
                answer = json.loads(resp.read().decode("utf-8"))
        finally:
            server.stop()
        self.assertEqual(answer["code"], "0")
        self.assertEqual(answer["data"]["cleared_task_code"], STUCK_TASK)
        self.assertNotIn("active_task", dispatcher.state)


if __name__ == "__main__":
    unittest.main()
