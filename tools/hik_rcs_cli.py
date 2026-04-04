from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.hik_rcs_bridge import HikRcsBridge
from core.hik_rcs_client import HikRcsClient
from core.path_utils import PROJECT_ROOT


CONFIG_PATH = PROJECT_ROOT / "configs" / "hik_rcs.json"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def make_client(config: dict) -> HikRcsClient:
    return HikRcsClient(config, PROJECT_ROOT / "outputs" / "runtime" / "hik_rcs")


def cmd_query_agv(args) -> None:
    client = make_client(load_config())
    payload = {}
    if args.map_short_name:
        payload["mapShortName"] = args.map_short_name
    response = client.query_agv_status(payload)
    print(json.dumps(response, ensure_ascii=False, indent=2))


def cmd_query_task(args) -> None:
    client = make_client(load_config())
    payload = {"taskCode": args.task_code}
    response = client.call_rpc("queryTaskStatus", payload)
    print(json.dumps(response, ensure_ascii=False, indent=2))


def cmd_lock_position(args) -> None:
    client = make_client(load_config())
    ind_bind = "1" if args.action == "enable" else "0"
    response = client.lock_position(
        req_code=client.make_req_code(f"lockPosition:{args.position_code}:{ind_bind}"),
        position_code=args.position_code,
        ind_bind=ind_bind,
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))


def cmd_call_rpc(args) -> None:
    client = make_client(load_config())
    payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    response = client.call_rpc(args.api_name, payload)
    print(json.dumps(response, ensure_ascii=False, indent=2))


def cmd_probe_bin(args) -> None:
    client = make_client(load_config())
    response = client.probe_ctnr_binding(
        ctnr_typ=args.ctnr_typ,
        probe_ctnr_code=args.probe_ctnr_code,
        stg_bin_code=args.stg_bin_code,
        position_code=args.position_code,
        bin_name=args.bin_name,
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))


def cmd_bind_zone(args) -> None:
    config = load_config()
    bridge = HikRcsBridge(config, PROJECT_ROOT)
    bridge.enabled = True
    bridge.dry_run = args.dry_run
    mapping = None
    for item in config.get("mappings", []):
        if str(item.get("camera_id")) == args.camera_id and str(item.get("zone_id")) == args.zone_id:
            mapping = dict(item)
            break
    if mapping is None:
        raise SystemExit(f"Mapping not found for {args.camera_id}:{args.zone_id}")
    mapping["enabled"] = True

    camera_payload = {
        "camera_id": args.camera_id,
        "camera_name": args.camera_id,
        "camera_type": "manual",
        "camera_health": "online",
        "timestamp": 0.0,
        "zones": [],
    }
    zone_payload = {
        "zone_id": args.zone_id,
        "state": args.state,
        "health": "online" if args.state != "unknown" else "unknown",
        "score": args.score,
        "binding": "bind" if args.state == "occupied" else "unbind" if args.state == "empty" else "unknown",
        "value": 1 if args.state == "occupied" else 0 if args.state == "empty" else None,
    }
    bridge.dispatch_zone_state(camera_payload, zone_payload, mapping)
    print(json.dumps(bridge._entry_for(mapping), ensure_ascii=False, indent=2))
    bridge.close()


def cmd_serve_callbacks(args) -> None:
    config = load_config()
    bridge = HikRcsBridge(config, PROJECT_ROOT)
    if bridge.callback_server is None:
        raise SystemExit("callback_server.enabled=false in configs/hik_rcs.json")
    print("Callback server running. Press Ctrl+C to stop.")
    try:
        while True:
            import time

            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HIK RCS integration helper CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    query_agv = sub.add_parser("query-agv", help="Call queryAgvStatus")
    query_agv.add_argument("--map-short-name", default="", help="Optional map alias")
    query_agv.set_defaults(func=cmd_query_agv)

    query_task = sub.add_parser("query-task", help="Call queryTaskStatus")
    query_task.add_argument("--task-code", required=True)
    query_task.set_defaults(func=cmd_query_task)

    lock_position = sub.add_parser("lock-position", help="Call lockPosition directly")
    lock_position.add_argument("--position-code", required=True)
    lock_position.add_argument("--action", required=True, choices=["enable", "disable"])
    lock_position.set_defaults(func=cmd_lock_position)

    call_rpc = sub.add_parser("call-rpc", help="Call a generic RCS RPC API with a JSON payload file")
    call_rpc.add_argument("api_name", help="RCS RPC API name, e.g. genAgvSchedulingTask")
    call_rpc.add_argument("payload_file", help="Path to a JSON payload file")
    call_rpc.set_defaults(func=cmd_call_rpc)

    probe_bin = sub.add_parser("probe-bin", help="Probe whether a pallet/bin is empty or already bound in RCS")
    probe_bin.add_argument("--ctnr-typ", required=True, help="Container type expected by bindCtnrAndBin")
    probe_bin.add_argument("--probe-ctnr-code", default="VISION_PROBE", help="Temporary probe container code")
    probe_bin.add_argument("--stg-bin-code", default="", help="Storage bin code if available")
    probe_bin.add_argument("--position-code", default="", help="Position code if available")
    probe_bin.add_argument("--bin-name", default="", help="Optional bin name")
    probe_bin.set_defaults(func=cmd_probe_bin)

    bind_zone = sub.add_parser("bind-zone", help="Simulate one Vision zone state and dispatch the mapped RCS action")
    bind_zone.add_argument("--camera-id", required=True)
    bind_zone.add_argument("--zone-id", required=True)
    bind_zone.add_argument("--state", required=True, choices=["occupied", "empty", "unknown"])
    bind_zone.add_argument("--score", type=float, default=1.0)
    bind_zone.add_argument("--dry-run", action="store_true")
    bind_zone.set_defaults(func=cmd_bind_zone)

    serve = sub.add_parser("serve-callbacks", help="Run only the callback server")
    serve.set_defaults(func=cmd_serve_callbacks)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
