import json
import time
import sys
from types import SimpleNamespace
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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.detail_window import DetailWindow
from core.camera_reader import CameraReader
from core.camera_runner import CameraRunner
from core.config import load_camera_configs, load_json_dict, load_rule_config
from core.frame_store import FrameStore, LiveFrame
from core.live_camera_processor import LiveCameraProcessor
from core.path_utils import PROJECT_ROOT, ensure_exists, resolve_project_path
from core.replay_camera_processor import ReplayCameraProcessor

APP_ICON_PATH = PROJECT_ROOT / "assets" / "rtc_logo.png"

CAMERA_CONFIG_PATH = PROJECT_ROOT / "configs" / "cameras.json"
GUI_CONFIG_PATH = PROJECT_ROOT / "configs" / "gui.json"
RULE_CONFIG_PATH = PROJECT_ROOT / "configs" / "rules.json"
AGV_DIR = PROJECT_ROOT / "outputs" / "agv"


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
            pass
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
            return CameraReader(camera_cfg.camera_id, camera_cfg.source_path, self.frame_store)
        source = str(ensure_exists(resolve_project_path(camera_cfg.source_path), "Video source"))
        return VideoFileReader(camera_cfg.camera_id, source, self.frame_store, target_fps=target_fps)

    def get_latest(self):
        return self.frame_store.get_latest(self.camera_cfg.camera_id)

    def close(self):
        self.reader.stop()


class DetailSession:
    def __init__(self, camera_cfg, rule_cfg, target_fps: float):
        self.camera_cfg = camera_cfg
        self.rule_cfg = rule_cfg
        self.target_fps = target_fps
        self.runner = CameraRunner(self._build_processor(), target_fps)
        self.runner.start()

    def _build_processor(self):
        if self.camera_cfg.source_type in {"rtsp", "live"}:
            return LiveCameraProcessor(PROJECT_ROOT, self.camera_cfg, self.rule_cfg)
        return ReplayCameraProcessor(PROJECT_ROOT, self.camera_cfg, self.rule_cfg, target_fps=self.target_fps)

    def get_latest(self):
        return self.runner.get_latest()

    def close(self):
        self.runner.stop()


class OriginMonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.gui_cfg = load_json_dict(GUI_CONFIG_PATH)
        self.source_fps = float(self.gui_cfg.get("source_fps", 25.0))
        self.target_interval = 1.0 / max(1.0, self.source_fps)
        self.rule_cfg = load_rule_config(RULE_CONFIG_PATH)

        self.camera_configs = [cfg for cfg in load_camera_configs(CAMERA_CONFIG_PATH) if cfg.enabled]
        self.slots = [OriginCameraSlot(cfg, target_fps=self.source_fps) for cfg in self.camera_configs]
        self.slot_map = {cfg.camera_id: slot for cfg, slot in zip(self.camera_configs, self.slots)}
        self.latest_frames = {}
        self.latest_frame_ids = {}
        self.detail_windows = {}
        self.detail_state = {}
        self.detail_sessions = {}

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
        self.timer.timeout.connect(self.update_views)
        self.timer.start(int(self.gui_cfg.get("origin_update_interval_ms", 40)))

    def on_tile_clicked(self, index: int):
        if index >= len(self.camera_configs):
            return

        camera_cfg = self.camera_configs[index]
        camera_id = camera_cfg.camera_id

        window = self.detail_windows.get(camera_id)
        if window is None:
            window = DetailWindow(camera_id)
            self.detail_windows[camera_id] = window

        session = self.detail_sessions.get(camera_id)
        if session is None:
            session = DetailSession(camera_cfg, self.rule_cfg, self.source_fps)
            self.detail_sessions[camera_id] = session

        result = session.get_latest()
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

            now_ts = time.time()
            state = self.detail_state.get(camera_id)
            if state is None:
                state = {"last_display_ts": 0.0}
                self.detail_state[camera_id] = state

            if (now_ts - state["last_display_ts"]) < self.target_interval:
                continue

            state["last_display_ts"] = now_ts
            self.latest_frame_ids[camera_id] = live_frame.frame_id
            self.latest_frames[camera_id] = live_frame.frame
            tile.set_title(f"{self.camera_configs[index].name} ({camera_id})")
            tile.set_frame(live_frame.frame)

        for camera_id, window in list(self.detail_windows.items()):
            if window is None or not window.isVisible():
                continue

            session = self.detail_sessions.get(camera_id)
            if session is None:
                continue

            now_ts = time.time()
            state = self.detail_state.get(f"detail:{camera_id}")
            if state is None:
                state = {"last_display_ts": 0.0}
                self.detail_state[f"detail:{camera_id}"] = state

            if (now_ts - state["last_display_ts"]) < self.target_interval:
                continue

            result = session.get_latest()
            if result is None:
                continue

            state["last_display_ts"] = now_ts
            window.update_result(result)

        for camera_id, window in list(self.detail_windows.items()):
            if window is not None and not window.isVisible():
                session = self.detail_sessions.pop(camera_id, None)
                if session is not None:
                    session.close()

    def closeEvent(self, event):
        for window in self.detail_windows.values():
            window.close()
        for slot in self.slots:
            slot.close()
        for session in self.detail_sessions.values():
            session.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = OriginMonitorWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
