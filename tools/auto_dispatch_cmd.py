from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BOOTSTRAP_ROOT = Path(__file__).resolve().parents[1]
if str(BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP_ROOT))

from core.auto_dispatch_ledger import write_json_atomic_local
from core.auto_dispatch_diagnostics import AutoDispatchDiagnostics
from core.auto_dispatch_runtime import AutoDispatchRuntime
from core.path_utils import PROJECT_ROOT, resolve_project_path


AUTO_CONFIG_PATH = PROJECT_ROOT / "configs" / "auto_dispatch.json"
HIK_CONFIG_PATH = PROJECT_ROOT / "configs" / "hik_rcs.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "runtime" / "auto_dispatch"


def make_runtime() -> AutoDispatchRuntime:
    return AutoDispatchRuntime(AUTO_CONFIG_PATH, HIK_CONFIG_PATH, PROJECT_ROOT)


def print_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def make_diagnostics(runtime: AutoDispatchRuntime | None = None) -> AutoDispatchDiagnostics:
    if runtime is None:
        runtime = make_runtime()
    return AutoDispatchDiagnostics(runtime.auto_config, runtime.hik_config, PROJECT_ROOT)


def cmd_plan(args) -> None:
    runtime = make_runtime()
    print_json(runtime.plan_once(mode=args.mode))


def cmd_tick(args) -> None:
    runtime = make_runtime()
    result = runtime.update()
    print_json(result)


def cmd_status(args) -> None:
    runtime = make_runtime()
    print_json(runtime.status())


def cmd_validate_config(args) -> None:
    runtime = make_runtime()
    report = make_diagnostics(runtime).validate_config()
    print_json(report)
    if args.strict and not report.get("ok", False):
        raise SystemExit(2)


def cmd_doctor(args) -> None:
    runtime = make_runtime()
    diagnostics = make_diagnostics(runtime)
    report = diagnostics.doctor_report(
        cameras_payload=runtime.load_latest_cameras_payload(),
        bridge_state=runtime.load_bridge_state(),
        active_records=runtime.ledger.active_records(),
        runtime_state=runtime.ledger.load_runtime_state(),
    )
    if args.output:
        path = diagnostics.write_doctor_report(report, args.output)
        report["written_to"] = str(path)
    elif args.write:
        path = diagnostics.write_doctor_report(report)
        report["written_to"] = str(path)
    print_json(report)
    if args.strict and not report.get("validation", {}).get("ok", False):
        raise SystemExit(2)


def cmd_simulate(args) -> None:
    runtime = make_runtime()
    diagnostics = make_diagnostics(runtime)
    if args.sequence:
        cameras_payload, bridge_state = diagnostics.build_simulated_payload(args.scenario)
        print_json(
            diagnostics.preview_sequence(
                cameras_payload=cameras_payload,
                bridge_state=bridge_state,
                max_tasks=args.max_tasks,
                mode=args.mode,
            )
        )
    else:
        print_json(diagnostics.simulate_plan(args.scenario, mode=args.mode))


def cmd_preview_sequence(args) -> None:
    runtime = make_runtime()
    diagnostics = make_diagnostics(runtime)
    print_json(
        diagnostics.preview_sequence(
            cameras_payload=runtime.load_latest_cameras_payload(),
            bridge_state=runtime.load_bridge_state(),
            max_tasks=args.max_tasks,
            mode=args.mode,
        )
    )


def cmd_build_task(args) -> None:
    runtime = make_runtime()
    batch_id = args.batch_id or f"B_PREVIEW_{int(time.time())}"
    reservation_id = args.reservation_id or f"R_PREVIEW_{int(time.time())}"
    task_code = args.task_code or f"VISION_{args.source}_TO_{args.dest}_PREVIEW"
    payload = runtime.task_client.build_task_payload(
        auto_config=runtime.auto_config,
        source_position=args.source,
        dest_position=args.dest,
        task_code=task_code,
        reservation_id=reservation_id,
        batch_id=batch_id,
        mode=args.mode,
    )
    request_hash = runtime.task_client.payload_hash(payload)
    req_code = runtime.task_client.make_req_code(f"auto-dispatch:{task_code}:{request_hash}")
    print_json(
        {
            "payload": payload,
            "validation_errors": runtime.task_client.validate_task_payload(payload),
            "request_hash": request_hash,
            "req_code": req_code,
        }
    )


def cmd_start_batch(args) -> None:
    runtime = make_runtime()
    command = {
        "command": "start_batch",
        "command_id": f"start_batch:{time.time_ns()}",
        "max_tasks": args.max_tasks,
        "requested_by": args.requested_by,
    }
    runtime.write_command(command)
    if args.tick:
        print_json(runtime.update())
    else:
        print_json({"accepted": True, "command": command})


def cmd_pause(args) -> None:
    runtime = make_runtime()
    command = {
        "command": "pause",
        "command_id": f"pause:{time.time_ns()}",
        "reason": args.reason,
    }
    runtime.write_command(command)
    print_json(runtime.update() if args.tick else {"accepted": True, "command": command})


def cmd_resume(args) -> None:
    runtime = make_runtime()
    command = {
        "command": "resume",
        "command_id": f"resume:{time.time_ns()}",
    }
    runtime.write_command(command)
    print_json(runtime.update() if args.tick else {"accepted": True, "command": command})


def cmd_stop(args) -> None:
    runtime = make_runtime()
    command = {
        "command": "stop",
        "command_id": f"stop:{time.time_ns()}",
        "reason": args.reason,
    }
    runtime.write_command(command)
    print_json(runtime.update() if args.tick else {"accepted": True, "command": command})


def cmd_clear_fault(args) -> None:
    runtime = make_runtime()
    command = {
        "command": "clear_fault",
        "command_id": f"clear_fault:{time.time_ns()}",
    }
    runtime.write_command(command)
    print_json(runtime.update() if args.tick else {"accepted": True, "command": command})


def cmd_manual_lock(args) -> None:
    config = json.loads(AUTO_CONFIG_PATH.read_text(encoding="utf-8-sig"))
    lock_path = resolve_project_path(str(config.get("manual_lock_path", "outputs/runtime/auto_dispatch/manual_lock.json")))
    payload = {
        "active": args.active,
        "reason": args.reason,
        "updated_at": round(time.time(), 3),
    }
    write_json_atomic_local(lock_path, payload)
    print_json({"path": str(lock_path), "payload": payload})


def cmd_mark_verified(args) -> None:
    runtime = make_runtime()
    record = runtime.ledger.find(args.reservation_id)
    if record is None:
        raise SystemExit(f"reservation not found: {args.reservation_id}")
    updated = runtime.ledger.update_record(
        args.reservation_id,
        state="verified",
        verified_at=round(time.time(), 3),
        last_error="operator_mark_verified",
    )
    runtime.ledger.append_event("operator_mark_verified", {"reservation_id": args.reservation_id, "reason": args.reason})
    print_json(updated)


def cmd_recover(args) -> None:
    runtime = make_runtime()
    record = runtime.ledger.find(args.reservation_id)
    if record is None:
        raise SystemExit(f"reservation not found: {args.reservation_id}")
    updated = runtime.ledger.update_record(
        args.reservation_id,
        state="operator_recovery_required",
        last_error=args.reason,
    )
    runtime.ledger.append_event("operator_recovery_required", {"reservation_id": args.reservation_id, "reason": args.reason})
    print_json(updated)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vision Phase 2 AMR pallet auto-dispatch CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Evaluate next PK -> FG candidate without side effects")
    plan.add_argument("--mode", default="semi_auto", choices=["semi_auto", "full_auto"])
    plan.set_defaults(func=cmd_plan)

    tick = sub.add_parser("tick", help="Run one auto-dispatch runtime tick")
    tick.set_defaults(func=cmd_tick)

    status = sub.add_parser("status", help="Show runtime state, active reservations, and latest snapshot")
    status.set_defaults(func=cmd_status)

    validate_config = sub.add_parser("validate-config", help="Validate Phase 2 config before enabling onsite")
    validate_config.add_argument("--strict", action="store_true", help="Exit non-zero when validation has errors")
    validate_config.set_defaults(func=cmd_validate_config)

    doctor = sub.add_parser("doctor", help="Export a complete Phase 2 onsite debug report")
    doctor.add_argument("--write", action="store_true", help="Write report under outputs/runtime/auto_dispatch/debug_reports")
    doctor.add_argument("--output", default="", help="Write report to a specific JSON path")
    doctor.add_argument("--strict", action="store_true", help="Exit non-zero when validation has errors")
    doctor.set_defaults(func=cmd_doctor)

    simulate = sub.add_parser("simulate", help="Run deterministic Phase 2 planner simulations")
    simulate.add_argument(
        "--scenario",
        default="full_pk_empty_fg",
        choices=[
            "full_pk_empty_fg",
            "site_partial_example",
            "parallel_after_human",
            "fg_full",
            "pk_empty",
            "unknown_source",
            "fg_not_canonical",
        ],
    )
    simulate.add_argument("--mode", default="semi_auto", choices=["semi_auto", "full_auto"])
    simulate.add_argument("--sequence", action="store_true", help="Preview a rolling FIFO/FILO sequence")
    simulate.add_argument("--max-tasks", type=int, default=12)
    simulate.set_defaults(func=cmd_simulate)

    preview_sequence = sub.add_parser("preview-sequence", help="Preview a rolling FIFO/FILO sequence from the current snapshot")
    preview_sequence.add_argument("--mode", default="semi_auto", choices=["semi_auto", "full_auto"])
    preview_sequence.add_argument("--max-tasks", type=int, default=12)
    preview_sequence.set_defaults(func=cmd_preview_sequence)

    build_task = sub.add_parser("build-task", help="Build a genAgvSchedulingTask payload without submitting")
    build_task.add_argument("--source", required=True)
    build_task.add_argument("--dest", required=True)
    build_task.add_argument("--mode", default="semi_auto", choices=["semi_auto", "full_auto"])
    build_task.add_argument("--batch-id", default="")
    build_task.add_argument("--reservation-id", default="")
    build_task.add_argument("--task-code", default="")
    build_task.set_defaults(func=cmd_build_task)

    start_batch = sub.add_parser("start-batch", help="Arm one semi-auto batch")
    start_batch.add_argument("--max-tasks", type=int, default=12)
    start_batch.add_argument("--requested-by", default="operator")
    start_batch.add_argument("--tick", action="store_true", help="Run one tick immediately after writing command")
    start_batch.set_defaults(func=cmd_start_batch)

    pause = sub.add_parser("pause", help="Pause dispatcher after current task")
    pause.add_argument("--reason", default="operator")
    pause.add_argument("--tick", action="store_true")
    pause.set_defaults(func=cmd_pause)

    resume = sub.add_parser("resume", help="Resume dispatcher from pause/fault after inspection")
    resume.add_argument("--tick", action="store_true")
    resume.set_defaults(func=cmd_resume)

    stop = sub.add_parser("stop", help="Stop current semi-auto batch")
    stop.add_argument("--reason", default="operator")
    stop.add_argument("--tick", action="store_true")
    stop.set_defaults(func=cmd_stop)

    clear_fault = sub.add_parser("clear-fault", help="Clear runtime fault after onsite recovery")
    clear_fault.add_argument("--tick", action="store_true")
    clear_fault.set_defaults(func=cmd_clear_fault)

    manual_lock = sub.add_parser("manual-lock", help="Set or clear manual interlock flag")
    manual_lock.add_argument("--active", action="store_true")
    manual_lock.add_argument("--inactive", action="store_false", dest="active")
    manual_lock.set_defaults(active=True)
    manual_lock.add_argument("--reason", default="operator")
    manual_lock.set_defaults(func=cmd_manual_lock)

    mark_verified = sub.add_parser("mark-verified", help="Operator marks a reservation verified after inspection")
    mark_verified.add_argument("--reservation-id", required=True)
    mark_verified.add_argument("--reason", default="operator")
    mark_verified.set_defaults(func=cmd_mark_verified)

    recover = sub.add_parser("recover", help="Move reservation to operator recovery state")
    recover.add_argument("--reservation-id", required=True)
    recover.add_argument("--reason", default="operator")
    recover.set_defaults(func=cmd_recover)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
