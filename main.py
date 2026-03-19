import torch
torch.backends.cudnn.benchmark = True

import time
import sys
from collections import deque
import threading

import cv2
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.detail_window import DetailWindow
from core.agv_exporter import AgvExporter
from core.camera_reader import CameraReader
from core.camera_runner import CameraRunner
from core.config import (
    load_camera_configs,
    load_json_dict,
    load_rule_config,
    validate_camera_configs,
    validate_gui_config,
    validate_rule_config,
)
from core.frame_store import FrameStore, LiveFrame
from core.history_logger import HistoryLogger
from core.live_camera_processor import LiveCameraProcessor
from core.logger_config import get_logger
from core.path_utils import PROJECT_ROOT, ensure_exists, resolve_project_path
from core.replay_camera_processor import ReplayCameraProcessor

APP_ICON_PATH = PROJECT_ROOT / "assets" / "rtc_logo.png"

CAMERA_CONFIG_PATH = PROJECT_ROOT / "configs" / "cameras.json"
GUI_CONFIG_PATH = PROJECT_ROOT / "configs" / "gui.json"
RULE_CONFIG_PATH = PROJECT_ROOT / "configs" / "rules.json"
AGV_DIR = PROJECT_ROOT / "outputs" / "agv"
HISTORY_DIR = PROJECT_ROOT / "outputs" / "history"
logger = get_logger(__name__)


class VideoFileReader:
    def __init__(self, camera_id: str, source: str, frame_store: FrameStore, target_fps: float | None = None) -> None:
        self.camera_id = camera_id
        self.source = source
        self.frame_store = frame_store
        self._running = False
        self._thread = None
        self._frame_id = 0
        self._cap = cv2.VideoCapture(self.source)
        self._target_fps = float(target_fps) if target_fps and target_fps > 0 else None
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        fallback_fps = float(fps) if fps and fps > 1e-3 else 25.0
        if self._target_fps:
            fallback_fps = self._target_fps
        self._fallback_interval = 1.0 / max(1.0, fallback_fps)
        self._base_wall = None
        self._base_msec = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()

    def _get_frame_msec(self) -> float:
        if self._target_fps:
            return float(self._frame_id) * self._fallback_interval * 1000.0
        pos_msec = self._cap.get(cv2.CAP_PROP_POS_MSEC)
        if pos_msec and pos_msec > 1e-3:
            return float(pos_msec)
        return float(self._frame_id) * self._fallback_interval * 1000.0

    def _reset_to_start(self) -> None:
        try:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        except Exception:
            logger.exception("Failed to reset video reader for %s", self.camera_id)
        self._frame_id = 0
        self._base_wall = None
        self._base_msec = None

    def _run(self) -> None:
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                self._reset_to_start()
                continue

            self._frame_id += 1
            frame_msec = self._get_frame_msec()
            now = time.time()

            if self._base_wall is None:
                self._base_wall = now
                self._base_msec = frame_msec
            else:
                target_msec = self._base_msec + (now - self._base_wall) * 1000.0
                while frame_msec < target_msec - 5.0:
                    ret, frame = self._cap.read()
                    if not ret:
                        self._reset_to_start()
                        break
                    self._frame_id += 1
                    frame_msec = self._get_frame_msec()

                if not ret:
                    continue

                ahead_ms = frame_msec - target_msec
                if ahead_ms > 1.0:
                    time.sleep(ahead_ms / 1000.0)

            self.frame_store.update(
                LiveFrame(
                    camera_id=self.camera_id,
                    frame_id=self._frame_id,
                    timestamp=time.time(),
                    frame=frame,
                )
            )


class OriginTile(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, tile_index: int, title: str, min_width: int, min_height: int):
        super().__init__()
        self.tile_index = tile_index
        self.last_frame_bgr = None

        self.setMinimumSize(min_width, min_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #1d1f23; border: 1px solid #3a3f46;")

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "background-color: #17191d; color: white; font-weight: 700; padding: 4px 8px;"
        )
        self.title_label.setFixedHeight(28)

        self.image_label = QLabel("No Signal")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; color: #aaaaaa;")
        self.image_label.setScaledContents(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label, 1)

    def set_title(self, text: str):
        self.title_label.setText(text)

    def set_frame(self, frame_bgr):
        self.last_frame_bgr = frame_bgr.copy() if frame_bgr is not None else None
        self._render()

    def set_empty(self, title: str):
        self.set_title(title)
        self.last_frame_bgr = None
        self.image_label.clear()
        self.image_label.setText("Unused")

    def _render(self):
        if self.last_frame_bgr is None:
            self.image_label.clear()
            self.image_label.setText("No Signal")
            return

        target_w = max(1, self.image_label.width())
        target_h = max(1, self.image_label.height())
        frame = self.last_frame_bgr
        src_h, src_w = frame.shape[:2]
        scale = min(1.0, target_w / src_w, target_h / src_h)
        new_w = max(1, int(src_w * scale))
        new_h = max(1, int(src_h * scale))
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        self.image_label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def mousePressEvent(self, event):
        self.clicked.emit(self.tile_index)
        super().mousePressEvent(event)


class OriginCameraSlot:
    def __init__(self, camera_cfg, target_fps: float | None = None):
        self.camera_cfg = camera_cfg
        self.frame_store = FrameStore()
        self.reader = self._build_reader(camera_cfg, target_fps)
        self.reader.start()

    def _build_reader(self, camera_cfg, target_fps: float | None = None):
        if camera_cfg.source_type in {"rtsp", "live"}:
            return CameraReader(
                camera_cfg.camera_id,
                camera_cfg.source_path,
                self.frame_store,
                expected_fps=target_fps,
            )
        source = str(ensure_exists(resolve_project_path(camera_cfg.source_path), "Video source"))
        return VideoFileReader(camera_cfg.camera_id, source, self.frame_store, target_fps=target_fps)

    def get_latest(self):
        return self.frame_store.get_latest(self.camera_cfg.camera_id)

    def close(self):
        self.reader.stop()


class OriginMonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.gui_cfg = load_json_dict(GUI_CONFIG_PATH)
        validate_gui_config(self.gui_cfg)
        self.source_fps = float(self.gui_cfg.get("source_fps", 25.0))
        self.update_interval_ms = int(round(1000.0 / max(1.0, self.source_fps)))
        self.max_result_staleness_sec = float(self.gui_cfg.get("max_result_staleness_sec", 1.0))
        self.metrics_log_interval_sec = float(self.gui_cfg.get("metrics_log_interval_sec", 10.0))
        self.rule_cfg = load_rule_config(RULE_CONFIG_PATH)
        validate_rule_config(self.rule_cfg)

        self.camera_configs = [cfg for cfg in load_camera_configs(CAMERA_CONFIG_PATH) if cfg.enabled]
        validate_camera_configs(self.camera_configs)
        self.slots = [OriginCameraSlot(cfg, target_fps=self.source_fps) for cfg in self.camera_configs]
        self.slot_by_camera_id = {
            cfg.camera_id: slot
            for cfg, slot in zip(self.camera_configs, self.slots)
        }

        self.processor_target_fps = float(self.gui_cfg.get("processor_target_fps", self.source_fps))
        if self.processor_target_fps <= 0:
            self.processor_target_fps = self.source_fps

        self.agv_output_interval_ms = int(self.gui_cfg.get("agv_output_interval_ms", 40))
        self.debug_frame_export_interval_ms = int(self.gui_cfg.get("debug_frame_export_interval_ms", 40))
        self.last_agv_export_ts = 0.0
        self.last_debug_export_ts = {}

        self.history_logger = HistoryLogger(HISTORY_DIR)
        self.last_logged_ts = {}
        self.metrics = {}
        self.last_metrics_log_ts = time.time()
        self.agv_exporter = AgvExporter(AGV_DIR)

        self.runners = [
            CameraRunner(self._build_processor(cfg), self.processor_target_fps)
            for cfg in self.camera_configs
        ]
        for runner in self.runners:
            runner.start()

        self.latest_frames = {}
        self.latest_frame_ids = {}
        self.latest_results = {}
        self.last_result_frame_ids = {}
        self.detail_windows = {}

        self.setWindowTitle("AGV CCTV Origin Monitor")
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        self.resize(1700, 980)

        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setSpacing(int(self.gui_cfg["grid_spacing"]))
        self.grid.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.grid_widget, 1)

        self.tiles = []
        total_tiles = int(self.gui_cfg["grid_rows"]) * int(self.gui_cfg["grid_cols"])

        for index in range(total_tiles):
            if index < len(self.camera_configs):
                title = self.camera_configs[index].name
            else:
                title = f"Empty {index + 1}"

            tile = OriginTile(
                tile_index=index,
                title=title,
                min_width=int(self.gui_cfg["cell_min_width"]),
                min_height=int(self.gui_cfg["cell_min_height"]),
            )
            tile.clicked.connect(self.on_tile_clicked)
            self.tiles.append(tile)

            row = index // int(self.gui_cfg["grid_cols"])
            col = index % int(self.gui_cfg["grid_cols"])
            self.grid.addWidget(tile, row, col)

        for row in range(int(self.gui_cfg["grid_rows"])):
            self.grid.setRowStretch(row, 1)
            self.grid.setRowMinimumHeight(row, int(self.gui_cfg["cell_min_height"]))

        for col in range(int(self.gui_cfg["grid_cols"])):
            self.grid.setColumnStretch(col, 1)
            self.grid.setColumnMinimumWidth(col, int(self.gui_cfg["cell_min_width"]))

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.update_views)
        self.timer.start(self.update_interval_ms)
        logger.info("OriginMonitorWindow started with %d cameras", len(self.camera_configs))

    def _build_processor(self, camera_cfg):
        if camera_cfg.source_type in {"rtsp", "live"}:
            slot = self.slot_by_camera_id.get(camera_cfg.camera_id)
            return LiveCameraProcessor(
                PROJECT_ROOT,
                camera_cfg,
                self.rule_cfg,
                expected_fps=self.source_fps,
                frame_store=slot.frame_store if slot is not None else None,
            )
        return ReplayCameraProcessor(PROJECT_ROOT, camera_cfg, self.rule_cfg, target_fps=self.source_fps)

    def _export_debug_frame(self, camera_id: str, debug_frame, now_ts: float) -> None:
        last_ts = self.last_debug_export_ts.get(camera_id, 0.0)
        if (now_ts - last_ts) * 1000.0 < self.debug_frame_export_interval_ms:
            return
        if debug_frame is None:
            return
        out_path = AGV_DIR / f"{camera_id}_debug.jpg"
        try:
            cv2.imwrite(str(out_path), debug_frame)
            self.last_debug_export_ts[camera_id] = now_ts
        except Exception:
            logger.exception("Failed to export debug frame for %s", camera_id)

    def _export_agv_snapshot(self, now_ts: float) -> None:
        cameras_payload = []
        for result in self.latest_results.values():
            stale = (now_ts - result["timestamp"]) > self.max_result_staleness_sec
            camera_health = result.get("camera_health", "unknown")
            states = result.get("current_states", [])
            hold = stale or camera_health != "online" or any(state.state == "unknown" for state in states)

            cameras_payload.append(
                {
                    "camera_id": result["camera_id"],
                    "camera_type": result["camera_type"],
                    "timestamp": result["timestamp"],
                    "health": "stale" if stale else camera_health,
                    "hold": hold,
                    "states": []
                    if stale
                    else [
                        {
                            "zone_id": state.zone_id,
                            "state": state.state,
                            "score": round(state.score, 4),
                            "health": state.health,
                        }
                        for state in states
                    ],
                    "detections": [] if stale else result.get("detections", []),
                }
            )

        payload = {
            "timestamp": now_ts,
            "camera_count": len(cameras_payload),
            "cameras": cameras_payload,
        }
        self.agv_exporter.export_snapshot(payload)
        for cam in cameras_payload:
            self.agv_exporter.export_camera(cam["camera_id"], cam)

    def _update_metrics(self, result: dict, detect_ms: float) -> None:
        camera_id = result["camera_id"]
        entry = self.metrics.get(camera_id)
        if entry is None:
            entry = {
                "frame_count": 0,
                "unknown_count": 0,
                "detect_ms": deque(maxlen=300),
                "last_ts": time.time(),
                "reconnect_count": 0,
            }
            self.metrics[camera_id] = entry

        entry["frame_count"] += 1
        entry["detect_ms"].append(detect_ms)
        states = result.get("current_states", [])
        if any(state.state == "unknown" for state in states):
            entry["unknown_count"] += 1

        health = result.get("camera_health", "unknown")
        if health in {"offline", "stale"}:
            entry["reconnect_count"] += 1

    def _log_metrics_if_due(self) -> None:
        now = time.time()
        if now - self.last_metrics_log_ts < self.metrics_log_interval_sec:
            return
        self.last_metrics_log_ts = now

        for camera_id, entry in self.metrics.items():
            dt = max(1e-3, now - entry["last_ts"])
            fps = entry["frame_count"] / dt
            unknown_ratio = entry["unknown_count"] / max(1, entry["frame_count"])
            samples = list(entry["detect_ms"])
            detect_p95 = 0.0
            if samples:
                samples.sort()
                detect_p95 = samples[int(0.95 * (len(samples) - 1))]

            logger.info(
                "[Metrics] %s fps=%.1f detect_p95=%.1fms unknown_ratio=%.2f reconnects=%d",
                camera_id,
                fps,
                detect_p95,
                unknown_ratio,
                entry["reconnect_count"],
            )

            entry["frame_count"] = 0
            entry["unknown_count"] = 0
            entry["detect_ms"].clear()
            entry["last_ts"] = now
            entry["reconnect_count"] = 0

    def on_tile_clicked(self, index: int):
        if index >= len(self.camera_configs):
            return

        camera_cfg = self.camera_configs[index]
        camera_id = camera_cfg.camera_id

        window = self.detail_windows.get(camera_id)
        if window is None:
            window = DetailWindow(camera_id)
            self.detail_windows[camera_id] = window

        result = self.latest_results.get(camera_id)
        if result is not None:
            window.update_result(result)

        window.show()
        window.raise_()
        window.activateWindow()

    def update_views(self):
        for index, tile in enumerate(self.tiles):
            if index >= len(self.slots):
                tile.set_empty(f"Empty {index + 1}")
                continue

            live_frame = self.slots[index].get_latest()
            if live_frame is None:
                tile.set_title(self.camera_configs[index].name)
                tile.set_frame(None)
                continue

            camera_id = self.camera_configs[index].camera_id
            last_id = self.latest_frame_ids.get(camera_id)
            if last_id == live_frame.frame_id:
                continue

            self.latest_frame_ids[camera_id] = live_frame.frame_id
            self.latest_frames[camera_id] = live_frame.frame
            tile.set_title(f"{self.camera_configs[index].name} ({camera_id})")
            tile.set_frame(live_frame.frame)

        for runner in self.runners:
            result = runner.get_latest()
            if result is None:
                continue

            camera_id = result["camera_id"]
            last_result_frame_id = self.last_result_frame_ids.get(camera_id)
            if last_result_frame_id == result["frame_id"]:
                continue
            self.last_result_frame_ids[camera_id] = result["frame_id"]
            self.latest_results[camera_id] = result

            last_ts = self.last_logged_ts.get(camera_id)
            if result["changed_states"] and result["timestamp"] != last_ts:
                self.history_logger.log_zone_states(
                    camera_id,
                    result["changed_states"],
                    result["timestamp"],
                )
                self.last_logged_ts[camera_id] = result["timestamp"]

            detect_ms = float(result.get("detect_ms", 0.0))
            self._update_metrics(result, detect_ms)
            self._export_debug_frame(camera_id, result.get("debug_frame"), time.time())

        for camera_id, window in list(self.detail_windows.items()):
            if window is None or not window.isVisible():
                continue

            result = self.latest_results.get(camera_id)
            if result is None:
                continue

            window.update_result(result)

        now_ts = time.time()
        if (now_ts - self.last_agv_export_ts) * 1000.0 >= self.agv_output_interval_ms:
            self._export_agv_snapshot(now_ts)
            self.last_agv_export_ts = now_ts
        self._log_metrics_if_due()

    def closeEvent(self, event):
        logger.info("Closing OriginMonitorWindow")
        for window in self.detail_windows.values():
            window.close()
        for runner in self.runners:
            runner.stop()
        for slot in self.slots:
            slot.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    try:
        window = OriginMonitorWindow()
    except ValueError as exc:
        QMessageBox.critical(None, "Config Error", str(exc))
        sys.exit(1)
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
