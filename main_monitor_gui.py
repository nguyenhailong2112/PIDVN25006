import sys
import time
from collections import deque

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

from core.agv_exporter import AgvExporter
from core.camera_runner import CameraRunner
from core.config import (
    load_camera_configs,
    load_json_dict,
    load_rule_config,
    validate_camera_configs,
    validate_gui_config,
    validate_rule_config,
)
from core.history_logger import HistoryLogger
from core.live_camera_processor import LiveCameraProcessor
from core.logger_config import get_logger
from core.path_utils import PROJECT_ROOT
from core.replay_camera_processor import ReplayCameraProcessor


APP_ICON_PATH = PROJECT_ROOT / "assets" / "rtc_logo.png"

CAMERA_CONFIG_PATH = PROJECT_ROOT / "configs" / "cameras.json"
RULE_CONFIG_PATH = PROJECT_ROOT / "configs" / "rules.json"
GUI_CONFIG_PATH = PROJECT_ROOT / "configs" / "gui.json"
HISTORY_DIR = PROJECT_ROOT / "outputs" / "history"
AGV_DIR = PROJECT_ROOT / "outputs" / "agv"
logger = get_logger(__name__)


class CameraTile(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, tile_index: int, title: str, min_width: int, min_height: int):
        super().__init__()
        self.tile_index = tile_index
        self.last_frame_bgr = None
        self.last_status_text = "Waiting..."

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(min_width, min_height)
        self.setMaximumSize(16777215, 16777215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._set_tile_style("#1d1f23", "#3a3f46")

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "background-color: #17191d; color: white; font-weight: 700; padding: 4px 8px;"
        )
        self.title_label.setFixedHeight(30)

        self.image_label = QLabel("No Signal")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; color: #aaaaaa;")
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setMinimumHeight(max(90, min_height - 80))
        self.image_label.setScaledContents(False)

        self.status_label = QLabel("Waiting...")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background-color: #17191d; color: #f0f0f0; padding: 4px 8px;"
        )
        self.status_label.setFixedHeight(44)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label, 1)
        layout.addWidget(self.status_label)

    def _set_tile_style(self, bg_color: str, border_color: str) -> None:
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
            }}
            """
        )

    def set_selected(self, selected: bool) -> None:
        if selected:
            self._set_tile_style("#1d1f23", "#5aa0ff")
        else:
            self._set_tile_style("#1d1f23", "#3a3f46")

    def set_alert_level(self, level: str, selected: bool = False) -> None:
        if selected:
            self._set_tile_style("#1d1f23", "#5aa0ff")
            return

        if level == "warning":
            self._set_tile_style("#2a2418", "#d1a300")
        elif level == "danger":
            self._set_tile_style("#2a1818", "#d9534f")
        else:
            self._set_tile_style("#1d1f23", "#3a3f46")

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def update_content(self, frame_bgr, status_text: str) -> None:
        self.last_frame_bgr = frame_bgr.copy() if frame_bgr is not None else None
        self.last_status_text = status_text
        self.status_label.setText(status_text)
        self._render_frame()

    def set_empty(self, title: str, message: str) -> None:
        self.set_title(title)
        self.last_frame_bgr = None
        self.image_label.clear()
        self.image_label.setText(message)
        self.status_label.setText("Unused")

    def _render_frame(self) -> None:
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
        self._render_frame()

    def mousePressEvent(self, event):
        self.clicked.emit(self.tile_index)
        super().mousePressEvent(event)


class MonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.gui_cfg = load_json_dict(GUI_CONFIG_PATH)
        validate_gui_config(self.gui_cfg)
        self.source_fps = float(self.gui_cfg.get("source_fps", 25.0))
        self.update_interval_ms = int(round(1000.0 / max(1.0, self.source_fps)))
        self.max_result_staleness_sec = float(self.gui_cfg.get("max_result_staleness_sec", 1.0))
        self.metrics_log_interval_sec = float(self.gui_cfg.get("metrics_log_interval_sec", 10.0))
        self.camera_configs = [cfg for cfg in load_camera_configs(CAMERA_CONFIG_PATH) if cfg.enabled]
        self.rule_cfg = load_rule_config(RULE_CONFIG_PATH)
        validate_camera_configs(self.camera_configs)
        validate_rule_config(self.rule_cfg)
        self.history_logger = HistoryLogger(HISTORY_DIR)
        self.last_logged_ts = {}

        self.last_tick_time = time.perf_counter()
        self.last_gui_fps = 0.0
        self.last_total_detect_ms = 0.0
        self.latest_results = {}
        self.last_display_frame_ids = {}
        self.metrics = {}
        self.last_metrics_log_ts = time.time()

        self.processor_target_fps = float(self.gui_cfg.get("processor_target_fps", self.source_fps))
        if self.processor_target_fps <= 0:
            self.processor_target_fps = self.source_fps

        self.agv_output_interval_ms = int(self.gui_cfg.get("agv_output_interval_ms", 40))
        self.debug_frame_export_interval_ms = int(self.gui_cfg.get("debug_frame_export_interval_ms", 40))
        self.last_agv_export_ts = 0.0
        self.last_debug_export_ts = {}
        self.agv_exporter = AgvExporter(AGV_DIR)

        self.runners = [
            CameraRunner(self._build_processor(cfg), self.processor_target_fps)
            for cfg in self.camera_configs
        ]
        for runner in self.runners:
            runner.start()
        logger.info("MonitorWindow started with %d cameras", len(self.runners))

        self.setWindowTitle(self.gui_cfg["window_title"])
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        self.resize(1700, 980)

        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setSpacing(int(self.gui_cfg["grid_spacing"]))
        self.grid.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.grid_widget, 1)

        self.legend_label = QLabel("Legend: OK=Normal | WARNING=Unknown | OFFLINE=No Signal")
        self.legend_label.setStyleSheet(
            "background-color: #17191d; color: #d0d0d0; padding: 6px 10px; border: 1px solid #2d3138;"
        )
        root_layout.addWidget(self.legend_label)

        self.tiles = []
        total_tiles = int(self.gui_cfg["grid_rows"]) * int(self.gui_cfg["grid_cols"])

        for index in range(total_tiles):
            if index < len(self.camera_configs):
                title = self.camera_configs[index].name
            else:
                title = f"Empty {index + 1}"

            tile = CameraTile(
                tile_index=index,
                title=title,
                min_width=int(self.gui_cfg["cell_min_width"]),
                min_height=int(self.gui_cfg["cell_min_height"]),
            )
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

    def _build_processor(self, camera_cfg):
        if camera_cfg.source_type in {"rtsp", "live"}:
            return LiveCameraProcessor(
                PROJECT_ROOT,
                camera_cfg,
                self.rule_cfg,
                expected_fps=self.source_fps,
            )
        return ReplayCameraProcessor(PROJECT_ROOT, camera_cfg, self.rule_cfg, target_fps=self.source_fps)

    def _make_short_status(self, states):
        if not states:
            return "general_monitoring"

        parts = []
        for state in states[:6]:
            parts.append(f"{state.zone_id}:{state.state}")
        return " | ".join(parts)

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

    def update_views(self):
        total_detect_ms = 0.0

        for index, tile in enumerate(self.tiles):
            if index >= len(self.runners):
                tile.set_empty(f"Empty {index + 1}", "Unused")
                continue

            result = self.runners[index].get_latest()
            if result is None:
                tile.set_alert_level("danger")
                tile.update_content(None, "OFFLINE | No frame")
                continue

            camera_id = result["camera_id"]
            last_displayed = self.last_display_frame_ids.get(camera_id)
            if last_displayed == result["frame_id"]:
                continue

            self.last_display_frame_ids[camera_id] = result["frame_id"]
            self.latest_results[index] = result

            last_ts = self.last_logged_ts.get(camera_id)
            if result["changed_states"] and result["timestamp"] != last_ts:
                self.history_logger.log_zone_states(
                    camera_id,
                    result["changed_states"],
                    result["timestamp"],
                )
                self.last_logged_ts[camera_id] = result["timestamp"]

            states = result["current_states"]
            camera_health = result.get("camera_health", "unknown")
            if camera_health != "online":
                summary = "OFFLINE"
            elif states and any(s.state == "unknown" for s in states):
                summary = "WARNING"
            else:
                summary = "OK"

            status_text = f"{summary} | {self._make_short_status(states)}"

            if summary == "OFFLINE":
                tile.set_alert_level("danger")
            elif summary == "WARNING":
                tile.set_alert_level("warning")
            else:
                tile.set_alert_level("normal")

            detect_ms = float(result.get("detect_ms", 0.0))
            total_detect_ms += detect_ms
            self._update_metrics(result, detect_ms)

            title = f"{result['camera_name']} ({camera_id})"
            tile.set_title(title)
            tile.update_content(result["debug_frame"], status_text)

            self._export_debug_frame(camera_id, result.get("debug_frame"), time.time())

        now = time.perf_counter()
        dt = now - self.last_tick_time
        if dt > 0:
            self.last_gui_fps = 1.0 / dt
        self.last_tick_time = now
        self.last_total_detect_ms = total_detect_ms

        now_ts = time.time()
        if (now_ts - self.last_agv_export_ts) * 1000.0 >= self.agv_output_interval_ms:
            self._export_agv_snapshot(now_ts)
            self.last_agv_export_ts = now_ts
        self._log_metrics_if_due()

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

    def closeEvent(self, event):
        logger.info("Closing MonitorWindow")
        for runner in self.runners:
            runner.stop()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    try:
        window = MonitorWindow()
    except ValueError as exc:
        QMessageBox.critical(None, "Config Error", str(exc))
        sys.exit(1)
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
