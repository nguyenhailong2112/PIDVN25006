from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = os.environ.get(
    "VISION_AUTO_DISPATCH_BASE_URL",
    "http://192.168.10.44:8023/service/rest/visionAutoDispatch",
).rstrip("/")


def _load_json_input(value: str | None, file_path: str | None) -> dict:
    if value and file_path:
        raise SystemExit("Use either --json or --json-file, not both.")
    if file_path:
        return json.loads(Path(file_path).read_text(encoding="utf-8-sig"))
    if value:
        return json.loads(value)
    return {}


def _request(method: str, url: str, payload: dict | None = None, timeout: float = 10.0) -> dict:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw) if raw else {"code": str(exc.code), "message": str(exc)}
        except json.JSONDecodeError:
            return {"code": str(exc.code), "message": raw or str(exc)}
    except Exception as exc:
        return {"code": "HTTP_ERROR", "message": str(exc)}


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_health(args: argparse.Namespace) -> None:
    _print(_request("GET", f"{args.base_url}/health", timeout=args.timeout))


def cmd_status(args: argparse.Namespace) -> None:
    _print(_request("GET", f"{args.base_url}/status", timeout=args.timeout))


def cmd_get_status(args: argparse.Namespace) -> None:
    _print(_request("POST", f"{args.base_url}/getStatus", payload={}, timeout=args.timeout))


def cmd_set_mode(args: argparse.Namespace) -> None:
    payload = _load_json_input(args.json, args.json_file)
    payload.setdefault("reqCode", args.req_code or "")
    payload.setdefault("operation_mode", args.mode)
    payload.setdefault("profile_id", args.profile_id)
    if args.updated_by:
        payload.setdefault("updated_by", args.updated_by)
    if args.note:
        payload.setdefault("note", args.note)
    _print(_request("POST", f"{args.base_url}/setMode", payload=payload, timeout=args.timeout))


def cmd_query_agv(args: argparse.Namespace) -> None:
    payload = _load_json_input(args.json, args.json_file)
    payload.setdefault("reqCode", args.req_code or "")
    if args.agv_code:
        payload.setdefault("agvCode", args.agv_code)
    if args.map_short_name:
        payload.setdefault("mapShortName", args.map_short_name)
    _print(_request("POST", f"{args.base_url}/queryAgvStatus", payload=payload, timeout=args.timeout))


def cmd_query_task(args: argparse.Namespace) -> None:
    payload = _load_json_input(args.json, args.json_file)
    payload.setdefault("reqCode", args.req_code or "")
    payload.setdefault("taskCode", args.task_code)
    if args.agv_code:
        payload.setdefault("agvCode", args.agv_code)
    _print(_request("POST", f"{args.base_url}/queryTaskStatus", payload=payload, timeout=args.timeout))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone Vision auto dispatch API tester")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Vision auto dispatch base URL")
    parser.add_argument("--timeout", type=float, default=10.0, help="Request timeout in seconds")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("health", help="GET /health")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("status", help="GET /status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("get-status", help="POST /getStatus")
    p.set_defaults(func=cmd_get_status)

    p = sub.add_parser("set-mode", help="POST /setMode")
    p.add_argument("--mode", required=True, choices=["manual", "auto"], help="operation_mode")
    p.add_argument("--profile-id", default="PK_AB", choices=["PK_AB", "PK_CD"], help="profile_id")
    p.add_argument("--req-code", default="", help="Optional reqCode")
    p.add_argument("--updated-by", default="third_party", help="updated_by")
    p.add_argument("--note", default="", help="note")
    p.add_argument("--json", default="", help="Raw JSON payload string")
    p.add_argument("--json-file", default="", help="Path to JSON payload file")
    p.set_defaults(func=cmd_set_mode)

    p = sub.add_parser("query-agv", help="POST /queryAgvStatus")
    p.add_argument("--req-code", default="", help="Optional reqCode")
    p.add_argument("--agv-code", default="16675", help="agvCode")
    p.add_argument("--map-short-name", default="", help="Optional mapShortName")
    p.add_argument("--json", default="", help="Raw JSON payload string")
    p.add_argument("--json-file", default="", help="Path to JSON payload file")
    p.set_defaults(func=cmd_query_agv)

    p = sub.add_parser("query-task", help="POST /queryTaskStatus")
    p.add_argument("--task-code", required=True, help="taskCode created by Vision")
    p.add_argument("--req-code", default="", help="Optional reqCode")
    p.add_argument("--agv-code", default="16675", help="agvCode")
    p.add_argument("--json", default="", help="Raw JSON payload string")
    p.add_argument("--json-file", default="", help="Path to JSON payload file")
    p.set_defaults(func=cmd_query_task)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.base_url = args.base_url.rstrip("/")
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
