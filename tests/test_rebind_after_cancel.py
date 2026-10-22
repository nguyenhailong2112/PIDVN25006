"""Bridge + dispatcher test for the 22/10 obstacle case.

A task picking PK_AA5 (slot cam4:A4, RCS bin A0000403501013) was canceled after the robot had
lifted the pallet. RCS then dropped PK_AA5 from the bin while the pallet stood in A4 again, and
Vision still believed the slot was bound. Next auto tasks sent the robot to A3 behind the pallet
in A4 and it stopped on an obstacle.

Run from the project root:
    python -m unittest tests.test_rebind_after_cancel -v

No network: the bridge and the dispatcher both talk to a fake RCS that keeps bin bindings.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ["PIDVN_LOG_DIR"] = tempfile.mkdtemp(prefix="pidvn_test_logs_")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auto_dispatcher import AutoDispatcher  # noqa: E402
from core.hik_rcs_bridge import HikRcsBridge  # noqa: E402
from tests.test_auto_dispatcher_task_status import load_amr_config  # noqa: E402

PK_AB = ["PK_AA5", "PK_AA3", "PK_AA2", "PK_AA1", "PK_BB4", "PK_BB3", "PK_BB2", "PK_BB1"]
A4_BIN = "A0000403501013"
T0 = 1792580000.0


class FakeRcsWithBins:
    """RCS double: bin bindings, task status, and the rejection messages seen on site."""

    def __init__(self) -> None:
        self.bins: dict[str, str] = {}
        self.locked_bins: set[str] = set()
        self.task_status: dict[str, str] = {}
        self.task_ctnr: dict[str, str] = {}
        self.created: list[dict] = []

    def call_rpc(self, api_name: str, payload: dict, req_code: str | None = None) -> dict:
        ok = {"code": "0", "message": "successful", "reqCode": req_code or "", "data": ""}
        if api_name == "bindCtnrAndBin":
            return self._bind(payload, ok)
        if api_name == "genAgvSchedulingTask":
            self.created.append(dict(payload))
            self.task_status[payload["taskCode"]] = "2"
            return {**ok, "data": payload["taskCode"]}
        if api_name == "queryTaskStatus":
            code = payload["taskCodes"][0]
            return {**ok, "data": [{"taskCode": code, "taskStatus": self.task_status.get(code, "2")}]}
        return ok  # lockPosition, blockArea

    def _bind(self, payload: dict, ok: dict) -> dict:
        ctnr, bin_code, ind = payload["ctnrCode"], payload["stgBinCode"], payload["indBind"]
        fail = lambda message: {"code": "1", "message": f"Fail to bind or unbind: {message}", "data": ""}  # noqa: E731
        if bin_code in self.locked_bins:
            return fail(f"Storage bin {bin_code} has been locked")
        if ctnr in self.task_ctnr.values():
            return fail(f"Container {ctnr} has incomplete task")
        current = self.bins.get(bin_code)
        if ind == "1":
            if current:
                return fail(f"Storage bin {bin_code} has bind container code {current}")
            self.bins[bin_code] = ctnr
            return ok
        if current != ctnr:
            return fail(f"Container {ctnr} not bound to this storage bin")
        del self.bins[bin_code]
        return ok


class RebindAfterCancelTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="pidvn_rebind_test_")
        self.root = Path(self._tmp.name)
        self.rcs = FakeRcsWithBins()
        hik = json.loads((PROJECT_ROOT / "configs" / "hik_rcs.json").read_text(encoding="utf-8-sig"))
        hik.update({"host": "127.0.0.1", "rpc_ports": [9], "rpc_port": 9, "dry_run": False, "enabled": True})
        hik["callback_server"] = {"enabled": False}
        self.bridge = HikRcsBridge(hik, self.root)
        self.bridge.client.call_rpc = self.rcs.call_rpc

        self.config = load_amr_config()
        runtime_dir = self.root / self.config["runtime_dir"]
        runtime_dir.mkdir(parents=True, exist_ok=True)
        self.set_mode("auto")
        self.dispatcher = AutoDispatcher(self.config, {"host": "127.0.0.1", "rpc_port": 9, "callback_server": {"enabled": True}}, self.root)
        self.dispatcher.client.call_rpc = self.rcs.call_rpc
        self.dispatcher.set_binding_rebinder(self.bridge.request_rebind)
        self.occupied = set(PK_AB)

    def tearDown(self) -> None:
        self.dispatcher.close()
        self.bridge.close()
        self._tmp.cleanup()

    def set_mode(self, mode: str) -> None:
        control = {"operation_mode": mode, "profile_id": "PK_AB", "updated_at": T0, "updated_by": "test", "note": ""}
        (self.root / self.config["control_state_path"]).write_text(json.dumps(control), encoding="utf-8")

    def cameras(self) -> list[dict]:
        by_camera: dict[str, list[dict]] = {}
        for position, pos_cfg in self.config["positions"].items():
            by_camera.setdefault(pos_cfg["camera_id"], []).append(
                {
                    "zone_id": pos_cfg["zone_id"],
                    "health": "online",
                    "score": 1.0,
                    "state": "occupied" if position in self.occupied else "empty",
                }
            )
        return [{"camera_id": cam, "camera_health": "online", "zones": zones} for cam, zones in by_camera.items()]

    def cycle(self, now_ts: float) -> dict:
        payload = self.cameras()
        self.bridge.sync(payload, now_ts)
        self.dispatcher.sync(payload, self.bridge.state, now_ts=now_ts)
        return self.dispatcher.state

    def a4_session(self) -> dict:
        return self.bridge.state["zones"]["cam4:A4:bindCtnrAndBin"]["hybrid_session"]

    def run_incident_until_cancel(self) -> str:
        state = self.cycle(T0)
        self.assertEqual(self.rcs.bins.get(A4_BIN), "PK_AA5")
        task_code = state["active_task"]["task_code"]
        self.assertEqual(state["active_task"]["source"], "PK_AA5")
        # Robot lifts the pallet: A4 looks empty, RCS refuses the unbind (task still running).
        self.rcs.task_ctnr[task_code] = "PK_AA5"
        self.occupied.discard("PK_AA5")
        self.cycle(T0 + 6)
        # Pallet ends up back in A4, then the task is canceled and RCS drops PK_AA5 from the bin.
        self.occupied.add("PK_AA5")
        self.cycle(T0 + 12)
        self.rcs.task_status[task_code] = "5"
        del self.rcs.task_ctnr[task_code]
        self.rcs.bins.pop(A4_BIN)
        return task_code

    def test_slot_is_rebound_after_cancel_and_auto_resumes_safely(self) -> None:
        task_code = self.run_incident_until_cancel()
        state = self.cycle(T0 + 18)
        self.assertEqual(state["status"], f"stopped_task_canceled:{task_code}")
        self.assertIn("PK_AA5", state.get("pending_rebind", []))

        state = self.cycle(T0 + 19)  # dispatcher hands the request to the bridge
        self.assertTrue(self.a4_session().get("rebind_pending"))
        self.cycle(T0 + 20)  # bridge re-asserts the binding with RCS
        self.assertEqual(self.rcs.bins.get(A4_BIN), "PK_AA5")
        self.assertNotIn("rebind_pending", self.a4_session())
        state = self.cycle(T0 + 21)
        self.assertNotIn("rebind_watch", state)

        self.dispatcher.set_control({"operation_mode": "auto", "profile_id": "PK_AB"}, now_ts=T0 + 30)
        state = self.cycle(T0 + 31)  # Auto press: all PK_AB slots are re-checked first
        self.assertEqual(state["status"], "blocked_bind_guard:PK_AA5:rebind_pending")
        state = self.cycle(T0 + 32)
        self.assertTrue(state["status"].startswith("task_created:QUANGPROPKAA5"), state["status"])

    def test_auto_press_repairs_drift_without_any_failed_task(self) -> None:
        """Drift already present on site (RCS lost A4, Vision thinks it is bound): Auto must not send the robot."""
        self.set_mode("manual")
        self.cycle(T0)
        self.assertEqual(self.rcs.bins.get(A4_BIN), "PK_AA5")
        self.rcs.bins.pop(A4_BIN)  # RCS loses the binding behind Vision's back
        self.cycle(T0 + 5)
        self.assertEqual(self.a4_session().get("actual_ctnr_code"), "PK_AA5")  # Vision still believes it

        self.set_mode("auto")
        self.dispatcher.set_control({"operation_mode": "auto", "profile_id": "PK_AB"}, now_ts=T0 + 10)
        state = self.cycle(T0 + 11)
        self.assertEqual(self.rcs.created, [])  # nothing sent before the re-check
        state = self.cycle(T0 + 12)
        self.assertEqual(self.rcs.bins.get(A4_BIN), "PK_AA5")
        self.assertTrue(state["status"].startswith("task_created:QUANGPROPKAA5"), state["status"])

    def test_auto_stays_blocked_while_rcs_refuses_the_rebind(self) -> None:
        self.run_incident_until_cancel()
        self.rcs.locked_bins.add(A4_BIN)  # e.g. bin locked on RCS
        for offset in (18, 19, 20, 26):
            self.cycle(T0 + offset)
        self.assertTrue(self.a4_session().get("rebind_pending"))
        self.assertIsNone(self.rcs.bins.get(A4_BIN))

        created_before = len(self.rcs.created)
        self.dispatcher.set_control({"operation_mode": "auto", "profile_id": "PK_AB"}, now_ts=T0 + 30)
        for offset in (31, 32, 40):
            state = self.cycle(T0 + offset)
        self.assertEqual(state["status"], "blocked_bind_guard:PK_AA5:rebind_pending")
        self.assertEqual(len(self.rcs.created), created_before)

        # Operator fixes RCS and presses Auto again: Vision re-checks and resumes.
        self.rcs.locked_bins.discard(A4_BIN)
        self.dispatcher.set_control({"operation_mode": "auto", "profile_id": "PK_AB"}, now_ts=T0 + 50)
        for offset in (51, 52, 53):
            state = self.cycle(T0 + offset)
        self.assertEqual(self.rcs.bins.get(A4_BIN), "PK_AA5")
        self.assertTrue(state["status"].startswith(("task_created:", "waiting_task:")), state["status"])
        self.assertEqual(len(self.rcs.created), created_before + 1)

    def test_other_slot_of_roadway_out_of_sync_blocks_task(self) -> None:
        """RCS picks by roadway: a mismatch on A2 must block the next task even though its source is A3."""
        self.cycle(T0)
        self.rcs.task_status[self.dispatcher.state["active_task"]["task_code"]] = "9"
        self.rcs.locked_bins.add("A0000203501013")
        self.bridge.request_rebind("cam4", "A2", reason="test", now_ts=T0 + 5)
        self.cycle(T0 + 6)  # task 1 completes, A2 rebind refused by RCS
        state = self.cycle(T0 + 7)
        self.assertEqual(state["status"], "blocked_bind_guard:PK_AA2:rebind_pending")
        self.assertEqual(len(self.rcs.created), 1)


if __name__ == "__main__":
    unittest.main()
