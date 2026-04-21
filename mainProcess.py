from __future__ import annotations

import json
import time
from dataclasses import dataclass
from threading import Lock, Thread
from datetime import datetime

import cv2

from core.camera_reader import CameraReader
from core.config import (
    load_camera_configs,
    load_ingest_config,
    load_json_dict,
    load_rule_config,
    validate_camera_configs,
    validate_ingest_config,
    validate_rule_config,
    load_zone_configs,
)
from core.elevator_runtime import ElevatorRuntime
from core.frame_store import FrameStore
from core.hik_rcs_bridge import HikRcsBridge
from core.history_logger import HistoryLogger
from core.logger_config import get_logger
from core.model_registry import ModelRegistry
from core.path_utils import PROJECT_ROOT, ensure_exists, resolve_project_path
from core.runtime_maintenance import RuntimeMaintenance
from core.runtime_bridge import (
    AGV_SNAPSHOT_PATH,
    PROCESS_SNAPSHOT_PATH,
    camera_debug_path,
    camera_preview_path,
    camera_snapshot_path,
    ensure_runtime_dirs,
    load_selected_cameras,
    write_image_atomic,
    write_json_atomic,
)
from core.state_tracker import StateTracker
from core.types import CameraConfig, Detection, DetectionResult
from core.video_file_reader import VideoFileReader
from core.visualizer import draw_debug_frame
from core.zone_reasoner import ZoneReasoner

CAMERA_CONFIG_PATH = PROJECT_ROOT / "configs" / "cameras.json"
RULE_CONFIG_PATH = PROJECT_ROOT / "configs" / "rules.json"
INGEST_CONFIG_PATH = PROJECT_ROOT / "configs" / "ingest.json"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime.json"
HIK_RCS_CONFIG_PATH = PROJECT_ROOT / "configs" / "hik_rcs.json"
ELEVATOR_CONFIG_PATH = PROJECT_ROOT / "configs" / "elevator.json"
HISTORY_DIR = PROJECT_ROOT / "outputs" / "history"
logger = get_logger(__name__)


@dataclass
class CameraWorker:
    camera_cfg: CameraConfig
    reader: CameraReader | VideoFileReader
    frame_store: FrameStore
    reasoner: ZoneReasoner | None
    tracker: StateTracker | None
    zone_configs: list
    last_infer_ts: float = 0.0
    last_inferred_frame_id: int = -1
    last_result_payload: dict | None = None
    last_preview_export_ts: float = 0.0
    last_debug_export_ts: float = 0.0

    def get_latest_frame(self):
        return self.frame_store.get_latest(self.camera_cfg.camera_id)

    def get_health(self) -> str:
        try:
            return self.reader.get_health()
        except Exception:
            return "unknown"


class CentralBackendRuntime:
    def __init__(self) -> None:
        ensure_runtime_dirs()
        self.camera_configs = [cfg for cfg in load_camera_configs(CAMERA_CONFIG_PATH) if cfg.enabled]
        self.rule_cfg = load_rule_config(RULE_CONFIG_PATH)
        self.ingest_cfg = load_ingest_config(INGEST_CONFIG_PATH)
        self.runtime_cfg = load_json_dict(RUNTIME_CONFIG_PATH)
        validate_camera_configs(self.camera_configs)
        validate_rule_config(self.rule_cfg)
        validate_ingest_config(self.ingest_cfg)

        history_log_max_bytes = max(
            0,
            int(float(self.runtime_cfg.get("history_log_max_mb", 10.0)) * 1024 * 1024),
        )
        history_log_backup_count = max(0, int(self.runtime_cfg.get("history_log_backup_count", 7)))
        self.history_logger = HistoryLogger(
            HISTORY_DIR,
            max_bytes=history_log_max_bytes,
            backup_count=history_log_backup_count,
        )
        self.last_logged_ts = {}
        self.export_interval_sec = max(0.02, float(self.runtime_cfg.get("export_interval_ms", 100)) / 1000.0)
        self.debug_export_interval_sec = 1.0 / max(1.0, float(self.runtime_cfg.get("debug_export_fps", 15.0)))
        self.preview_export_interval_sec = 1.0 / max(1.0, float(self.runtime_cfg.get("grid_display_fps", 10.0)))
        self.schedule_sleep_sec = max(0.001, float(self.runtime_cfg.get("schedule_sleep_ms", 5)) / 1000.0)
        self.selected_priority_boost = float(self.runtime_cfg.get("selected_priority_boost", 1000.0))
        self.detail_priority_boost = float(self.runtime_cfg.get("detail_priority_boost", 1200.0))
        self.offline_priority_penalty = max(0.0, float(self.runtime_cfg.get("offline_priority_penalty", 0.2)))
        self.decode_fps_default = float(self.runtime_cfg.get("decode_fps_default", self.ingest_cfg.reader_output_fps))
        self.selected_infer_fps = float(self.runtime_cfg.get("selected_infer_fps", 15.0))
        self.detail_infer_fps = float(self.runtime_cfg.get("detail_infer_fps", self.selected_infer_fps))
        self.slot_infer_fps_default = float(self.runtime_cfg.get("slot_infer_fps_default", 10.0))
        self.general_infer_fps_default = float(self.runtime_cfg.get("general_infer_fps_default", 5.0))
        self.preview_width = int(self.runtime_cfg.get("preview_width", 960))
        self.preview_height = int(self.runtime_cfg.get("preview_height", 540))
        self.occupied_session_break_sec = max(0.0, float(self.runtime_cfg.get("occupied_session_break_sec", 5.0)))
        self.last_export_ts = 0.0

        self.workers = [self._build_worker(cfg) for cfg in self.camera_configs]
        self.model_bundles = {}
        self.elevator_runtime = ElevatorRuntime(ELEVATOR_CONFIG_PATH)
        self.runtime_maintenance = RuntimeMaintenance(PROJECT_ROOT, self.runtime_cfg)
        self.hik_bridge = HikRcsBridge(load_json_dict(HIK_RCS_CONFIG_PATH), PROJECT_ROOT)
        self._hik_sync_lock = Lock()
        self._hik_sync_worker: Thread | None = None
        self._hik_sync_running = False
        self._hik_sync_payload: list[dict] | None = None
        self._hik_sync_timestamp: float | None = None
        self.zone_occupied_since_ts: dict[str, float] = {}
        self.zone_empty_since_ts: dict[str, float] = {}
        logger.info("CentralBackendRuntime started with %d cameras", len(self.workers))

    def _decode_fps_for(self, camera_cfg) -> float:
        return max(self.decode_fps_default, float(self.ingest_cfg.reader_output_fps))

    def _build_reader(self, camera_cfg, frame_store: FrameStore):
        decode_fps = self._decode_fps_for(camera_cfg)
        if camera_cfg.source_type in {"rtsp", "live"}:
            reader = CameraReader(
                camera_cfg.camera_id,
                camera_cfg.source_path,
                frame_store,
                expected_fps=decode_fps,
                ingest_config=self.ingest_cfg,
            )
        else:
            source = str(ensure_exists(resolve_project_path(camera_cfg.source_path), "Video source"))
            reader = VideoFileReader(camera_cfg.camera_id, source, frame_store, target_fps=decode_fps)
        reader.start()
        return reader

    def _build_worker(self, camera_cfg) -> CameraWorker:
        frame_store = FrameStore()
        reader = self._build_reader(camera_cfg, frame_store)
        zone_configs = []
        reasoner = None
        tracker = None
        if camera_cfg.zone_config:
            zone_config_path = ensure_exists(camera_cfg.zone_config, "Zone config")
            zone_configs = load_zone_configs(zone_config_path)
            reasoner = ZoneReasoner(zone_configs, self.rule_cfg)
            tracker = StateTracker(self.rule_cfg)
        return CameraWorker(camera_cfg, reader, frame_store, reasoner, tracker, zone_configs)

    def _get_model_bundle(self, camera_cfg):
        model_path = str(ensure_exists(camera_cfg.model_path, "Model file"))
        bundle = self.model_bundles.get(model_path)
        if bundle is None:
            bundle = ModelRegistry.get(model_path)
            self.model_bundles[model_path] = bundle
        return bundle

    def _target_infer_fps(self, worker: CameraWorker, selected_cameras: set[str]) -> float:
        if worker.camera_cfg.camera_id in selected_cameras:
            base_fps = self.detail_infer_fps
        elif worker.reasoner is not None:
            base_fps = self.slot_infer_fps_default
        else:
            base_fps = self.general_infer_fps_default
        infer_every_n_frames = max(1, int(worker.camera_cfg.infer_every_n_frames))
        return max(0.1, base_fps / infer_every_n_frames)

    def _make_due_score(self, worker: CameraWorker, selected_cameras: set[str], now_ts: float) -> float | None:
        live_frame = worker.get_latest_frame()
        if live_frame is None:
            return None
        if live_frame.frame_id == worker.last_inferred_frame_id:
            return None

        target_fps = max(0.1, self._target_infer_fps(worker, selected_cameras))
        target_interval = 1.0 / target_fps
        elapsed = now_ts - worker.last_infer_ts
        if elapsed < target_interval * 0.6:
            return None

        score = elapsed / target_interval
        if worker.camera_cfg.camera_id in selected_cameras:
            score += self.selected_priority_boost + self.detail_priority_boost
        if worker.get_health() != "online":
            score *= self.offline_priority_penalty
        return score

    def _select_due_workers(self, selected_cameras: set[str], now_ts: float) -> list[CameraWorker]:
        due = []
        for worker in self.workers:
            score = self._make_due_score(worker, selected_cameras, now_ts)
            if score is not None:
                due.append((score, worker))
        due.sort(key=lambda item: item[0], reverse=True)
        return [worker for _, worker in due[: max(1, int(self.rule_cfg.batch_size))]]

    def _run_batch_inference(self, workers: list[CameraWorker]) -> list[tuple[CameraWorker, DetectionResult, float]]:
        if not workers:
            return []

        groups: dict[str, list[CameraWorker]] = {}
        for worker in workers:
            model_path = str(ensure_exists(worker.camera_cfg.model_path, "Model file"))
            groups.setdefault(model_path, []).append(worker)

        processed = []
        for group in groups.values():
            bundle = self._get_model_bundle(group[0].camera_cfg)
            frames = []
            live_frames = []
            for worker in group:
                live_frame = worker.get_latest_frame()
                if live_frame is None:
                    continue
                frames.append(live_frame.frame)
                live_frames.append((worker, live_frame))
            if not frames:
                continue

            t0 = time.perf_counter()
            results = bundle.model.predict(
                frames,
                conf=self.rule_cfg.conf_threshold,
                imgsz=self.rule_cfg.img_size,
                verbose=False,
                device=0,
            )
            detect_ms = ((time.perf_counter() - t0) * 1000.0) / max(1, len(live_frames))
            for (worker, live_frame), result in zip(live_frames, results):
                detections = []
                if hasattr(result, "boxes"):
                    for box in result.boxes:
                        cls_id = int(box.cls[0])
                        class_name = bundle.model.names[cls_id]
                        confidence = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        detections.append(Detection(class_name=class_name, confidence=confidence, bbox_xyxy=(x1, y1, x2, y2)))
                processed.append(
                    (
                        worker,
                        DetectionResult(
                            camera_id=worker.camera_cfg.camera_id,
                            frame_id=live_frame.frame_id,
                            timestamp=live_frame.timestamp,
                            detections=detections,
                        ),
                        detect_ms,
                    )
                )
        return processed

    @staticmethod
    def _format_wall_clock(ts: float | None) -> str | None:
        if ts is None:
            return None
        try:
            return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
        except Exception:
            return None

    @staticmethod
    def _zone_key(camera_id: str, zone_id: str) -> str:
        return f"{camera_id}:{zone_id}"

    def _zone_state_payload(self, state, occupied_since_ts: float | None = None) -> dict:
        if state.state == "occupied":
            value = 1
            binding = "bind"
        elif state.state == "empty":
            value = 0
            binding = "unbind"
        else:
            value = None
            binding = "unknown"
        return {
            "zone_id": state.zone_id,
            "value": value,
            "binding": binding,
            "state": state.state,
            "health": state.health,
            "score": round(float(state.score), 4),
            "occupied_since_ts": occupied_since_ts,
            "occupied_since_text": self._format_wall_clock(occupied_since_ts),
        }

    def _update_occupied_since(self, states: list) -> None:
        for state in states:
            key = self._zone_key(state.camera_id, state.zone_id)
            if state.state == "occupied":
                self.zone_occupied_since_ts.setdefault(key, float(state.timestamp))
                self.zone_empty_since_ts.pop(key, None)
            elif state.state == "empty":
                if key not in self.zone_occupied_since_ts:
                    self.zone_empty_since_ts.pop(key, None)
                    continue
                empty_since_ts = self.zone_empty_since_ts.setdefault(key, float(state.timestamp))
                if self.occupied_session_break_sec <= 0.0 or (float(state.timestamp) - empty_since_ts) >= self.occupied_session_break_sec:
                    self.zone_occupied_since_ts.pop(key, None)
                    self.zone_empty_since_ts.pop(key, None)
            else:
                self.zone_empty_since_ts.pop(key, None)

    def _clear_stale_occupied_tracking(self, camera_id: str, active_zone_keys: set[str]) -> None:
        prefix = f"{camera_id}:"
        for key in list(self.zone_occupied_since_ts.keys()):
            if not key.startswith(prefix):
                continue
            if key not in active_zone_keys:
                self.zone_occupied_since_ts.pop(key, None)
                self.zone_empty_since_ts.pop(key, None)

    def _empty_payload(self, worker: CameraWorker, live_frame) -> dict:
        return {
            "camera_id": worker.camera_cfg.camera_id,
            "camera_name": worker.camera_cfg.name,
            "camera_type": worker.camera_cfg.camera_type,
            "camera_health": worker.get_health(),
            "frame_id": live_frame.frame_id if live_frame is not None else -1,
            "timestamp": live_frame.timestamp if live_frame is not None else 0.0,
            "detect_ms": 0.0,
            "zones": [],
            "agv_answer": [],
            "detected_classes": [],
            "debug_enabled": False,
            "debug_frame": None,
        }

    def _update_worker_result(self, worker: CameraWorker, detection_result: DetectionResult, detect_ms: float, selected_cameras: set[str]) -> None:
        live_frame = worker.get_latest_frame()
        if live_frame is None:
            return

        current_states = []
        changed_states = []
        if worker.reasoner is not None and worker.tracker is not None:
            observations = worker.reasoner.observe(detection_result, live_frame.frame.shape)
            changed_states = worker.tracker.update_observations(observations)
            current_states = worker.tracker.get_current_states(worker.camera_cfg.camera_id, live_frame.timestamp)
            if changed_states:
                last_ts = self.last_logged_ts.get(worker.camera_cfg.camera_id)
                if live_frame.timestamp != last_ts:
                    self.history_logger.log_zone_states(worker.camera_cfg.camera_id, changed_states, live_frame.timestamp)
                    self.last_logged_ts[worker.camera_cfg.camera_id] = live_frame.timestamp

        self._update_occupied_since(current_states)
        self._clear_stale_occupied_tracking(
            worker.camera_cfg.camera_id,
            {self._zone_key(state.camera_id, state.zone_id) for state in current_states},
        )
        zone_detected_classes: dict[str, list[str]] = {}
        if worker.reasoner is not None and worker.camera_cfg.camera_type == "elevator":
            frame_height, frame_width = live_frame.frame.shape[:2]
            for zone in worker.zone_configs:
                spatial_method = zone.spatial_method or self.rule_cfg.spatial_method
                matched_classes = {
                    det.class_name.strip().lower()
                    for det in detection_result.detections
                    if det.class_name
                    and det.class_name.strip()
                    and worker.reasoner._matches_target_object(zone.target_object, det.class_name)
                    and worker.reasoner._match_detection_to_zone(
                        det.bbox_xyxy,
                        zone.polygon,
                        frame_width,
                        frame_height,
                        spatial_method,
                    )
                }
                zone_detected_classes[zone.zone_id] = sorted(matched_classes)
        zones = []
        for state in current_states:
            zone_key = self._zone_key(state.camera_id, state.zone_id)
            occupied_since_ts = self.zone_occupied_since_ts.get(zone_key)
            zone_payload = self._zone_state_payload(state, occupied_since_ts=occupied_since_ts)
            if state.zone_id in zone_detected_classes:
                zone_payload["detected_classes"] = zone_detected_classes[state.zone_id]
            zones.append(zone_payload)
        detected_classes = sorted(
            {
                det.class_name.strip().lower()
                for det in detection_result.detections
                if det.class_name and det.class_name.strip()
            }
        )
        debug_frame = None
        if worker.camera_cfg.camera_id in selected_cameras:
            debug_frame = draw_debug_frame(live_frame.frame, detection_result, worker.zone_configs, current_states)

        worker.last_infer_ts = live_frame.timestamp
        worker.last_inferred_frame_id = live_frame.frame_id
        worker.last_result_payload = {
            "camera_id": worker.camera_cfg.camera_id,
            "camera_name": worker.camera_cfg.name,
            "camera_type": worker.camera_cfg.camera_type,
            "camera_health": worker.get_health(),
            "frame_id": live_frame.frame_id,
            "timestamp": live_frame.timestamp,
            "detect_ms": detect_ms,
            "zones": zones,
            "agv_answer": zones,
            "detected_classes": detected_classes,
            "debug_enabled": worker.camera_cfg.camera_id in selected_cameras,
            "debug_frame": debug_frame,
        }

    def _export_preview_if_due(self, worker: CameraWorker, now_ts: float) -> None:
        live_frame = worker.get_latest_frame()
        if live_frame is None:
            return
        if (now_ts - worker.last_preview_export_ts) < self.preview_export_interval_sec:
            return
        preview = cv2.resize(live_frame.frame.copy(), (self.preview_width, self.preview_height), interpolation=cv2.INTER_AREA)
        write_image_atomic(camera_preview_path(worker.camera_cfg.camera_id), preview)
        worker.last_preview_export_ts = now_ts

    def _export_worker_snapshot(self, worker: CameraWorker, selected_cameras: set[str], now_ts: float) -> dict:
        live_frame = worker.get_latest_frame()
        payload = worker.last_result_payload or self._empty_payload(worker, live_frame)
        camera_id = worker.camera_cfg.camera_id
        self._export_preview_if_due(worker, now_ts)

        debug_requested = camera_id in selected_cameras
        debug_path = camera_debug_path(camera_id)
        if debug_requested and payload.get("debug_frame") is not None and (now_ts - worker.last_debug_export_ts) >= self.debug_export_interval_sec:
            write_image_atomic(debug_path, payload["debug_frame"])
            worker.last_debug_export_ts = now_ts

        export_payload = {key: value for key, value in payload.items() if key != "debug_frame"}
        export_payload["debug_enabled"] = debug_requested
        export_payload["debug_frame_path"] = str(debug_path) if debug_requested else None
        export_payload["preview_frame_path"] = str(camera_preview_path(camera_id))
        write_json_atomic(camera_snapshot_path(camera_id), export_payload, indent=None)
        return export_payload

    def _export_agv_snapshot(self, cameras_payload: list[dict], now_ts: float) -> None:
        agv_payload = {
            "timestamp": now_ts,
            "cameras": [
                {
                    "camera_id": payload["camera_id"],
                    "camera_name": payload["camera_name"],
                    "camera_type": payload["camera_type"],
                    "health": payload.get("camera_health", "unknown"),
                    "zones": payload.get("agv_answer", payload.get("zones", [])),
                }
                for payload in cameras_payload
            ],
        }
        write_json_atomic(AGV_SNAPSHOT_PATH, agv_payload, indent=None)

    @staticmethod
    def _elevator_zone_payload_from_snapshot(snapshot: dict) -> dict:
        fault_active = bool(snapshot.get("fault_active", False))
        entry_clear = bool(snapshot.get("entry_clear", False))
        if fault_active:
            state = "unknown"
            health = "unknown"
            score = 0.0
            binding = "unknown"
            value = None
        elif entry_clear:
            state = "empty"
            health = "online"
            score = 1.0
            binding = "unbind"
            value = 0
        else:
            state = "occupied"
            health = "online"
            score = 1.0
            binding = "bind"
            value = 1
        return {
            "zone_id": snapshot.get("zone_id", ""),
            "state": state,
            "health": health,
            "score": score,
            "binding": binding,
            "value": value,
            "lift_state": snapshot.get("lift_state", ""),
            "safety_ok": bool(snapshot.get("safety_ok", False)),
            "entry_clear": entry_clear,
            "intrusion_alarm": bool(snapshot.get("intrusion_alarm", False)),
            "fault_code": snapshot.get("fault_code", ""),
        }

    def _build_control_payload(self, cameras_payload: list[dict], elevator_payload: dict) -> list[dict]:
        elevator_map = {
            str(item.get("camera_id", "")): item
            for item in elevator_payload.get("lifts", [])
            if isinstance(item, dict)
        }
        if not elevator_map:
            return cameras_payload

        hik_payload = []
        for payload in cameras_payload:
            camera_id = str(payload.get("camera_id", ""))
            snapshot = elevator_map.get(camera_id)
            if snapshot is None:
                hik_payload.append(payload)
                continue

            zone_id = str(snapshot.get("zone_id", ""))
            replaced_zone = self._elevator_zone_payload_from_snapshot(snapshot)
            zones = []
            replaced = False
            for zone in payload.get("zones", []):
                if str(zone.get("zone_id", "")) == zone_id:
                    zones.append(replaced_zone)
                    replaced = True
                else:
                    zones.append(dict(zone))
            if not replaced:
                zones.append(replaced_zone)

            updated_payload = dict(payload)
            updated_payload["zones"] = zones
            updated_payload["elevator_state"] = snapshot.get("lift_state", "")
            updated_payload["elevator_entry_clear"] = bool(snapshot.get("entry_clear", False))
            updated_payload["elevator_intrusion_alarm"] = bool(snapshot.get("intrusion_alarm", False))
            hik_payload.append(updated_payload)
        return hik_payload

    def run(self) -> None:
        while True:
            now_ts = time.time()
            selected_cameras = load_selected_cameras()
            due_workers = self._select_due_workers(selected_cameras, now_ts)
            processed = self._run_batch_inference(due_workers)
            for worker, detection_result, detect_ms in processed:
                self._update_worker_result(worker, detection_result, detect_ms, selected_cameras)

            if (now_ts - self.last_export_ts) >= self.export_interval_sec:
                cameras_payload = [self._export_worker_snapshot(worker, selected_cameras, now_ts) for worker in self.workers]
                elevator_payload = self.elevator_runtime.update(cameras_payload, now_ts)
                write_json_atomic(
                    PROCESS_SNAPSHOT_PATH,
                    {
                        "timestamp": now_ts,
                        "camera_count": len(cameras_payload),
                        "cameras": cameras_payload,
                        "elevators": elevator_payload.get("lifts", []),
                    },
                    indent=None,
                )
                control_payload = self._build_control_payload(cameras_payload, elevator_payload)
                self._export_agv_snapshot(control_payload, now_ts)
                self._schedule_hik_sync(control_payload, now_ts)
                self.runtime_maintenance.run_if_due(now_ts)
                self.last_export_ts = now_ts

            time.sleep(self.schedule_sleep_sec)

    def close(self) -> None:
        self._wait_hik_sync_worker(timeout_sec=2.0)
        try:
            self.hik_bridge.close()
        except Exception:
            logger.exception("Failed to close HIK bridge cleanly")
        for worker in self.workers:
            worker.reader.stop()

    def _schedule_hik_sync(self, cameras_payload: list[dict], now_ts: float) -> None:
        with self._hik_sync_lock:
            self._hik_sync_payload = cameras_payload
            self._hik_sync_timestamp = now_ts
            if self._hik_sync_running:
                return
            self._hik_sync_running = True
            self._hik_sync_worker = Thread(target=self._hik_sync_loop, daemon=True)
            self._hik_sync_worker.start()

    def _hik_sync_loop(self) -> None:
        while True:
            with self._hik_sync_lock:
                payload = self._hik_sync_payload
                timestamp = self._hik_sync_timestamp
                self._hik_sync_payload = None
                self._hik_sync_timestamp = None
            if payload is None or timestamp is None:
                with self._hik_sync_lock:
                    self._hik_sync_running = False
                    self._hik_sync_worker = None
                return
            try:
                self.hik_bridge.sync(payload, timestamp)
            except Exception:
                logger.exception("HIK bridge async sync failed")

    def _wait_hik_sync_worker(self, timeout_sec: float) -> None:
        worker = self._hik_sync_worker
        if worker is None:
            return
        worker.join(timeout=max(0.0, float(timeout_sec)))


def main() -> None:
    runtime = CentralBackendRuntime()
    try:
        runtime.run()
    except KeyboardInterrupt:
        logger.info("CentralBackendRuntime interrupted by user")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
