import json
import sys
import time
import numpy as np

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
from core.config import load_camera_configs, load_json_dict, validate_camera_configs, validate_gui_config
from core.logger_config import get_logger
from core.path_utils import PROJECT_ROOT
from core.runtime_bridge import camera_debug_path, camera_preview_path, camera_snapshot_path, load_selected_cameras, save_selected_cameras

APP_ICON_PATH = PROJECT_ROOT / "assets" / "rtc_logo.png"
CAMERA_CONFIG_PATH = PROJECT_ROOT / "configs" / "cameras.json"
GUI_CONFIG_PATH = PROJECT_ROOT / "configs" / "gui.json"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime.json"
logger = get_logger(__name__)


class ImageTile(QFrame):
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

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def set_frame(self, frame_bgr) -> None:
        self.last_frame_bgr = frame_bgr
        self._render()

    def set_empty(self, title: str) -> None:
        self.set_title(title)
        self.last_frame_bgr = None
        self.image_label.clear()
        self.image_label.setText("Unused")

    def _render(self) -> None:
        if self.last_frame_bgr is None:
            self.image_label.clear()
            self.image_label.setText("No Signal")
            return

        target_size = self.image_label.size()
        target_w = max(1, target_size.width())
        target_h = max(1, target_size.height())
        frame = self.last_frame_bgr
        src_h, src_w = frame.shape[:2]
        scale = min(1.0, target_w / src_w, target_h / src_h)
        new_w = max(1, int(src_w * scale))
        new_h = max(1, int(src_h * scale))
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)

        # center ảnh vào giữa
        x_offset = (target_w - new_w) // 2
        y_offset = (target_h - new_h) // 2

        canvas[y_offset:y_offset + new_h, x_offset:x_offset + new_w] = resized

        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape

        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(image)

        self.image_label.setPixmap(
            pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def mousePressEvent(self, event):
        self.clicked.emit(self.tile_index)
        super().mousePressEvent(event)


class CctvMonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.gui_cfg = load_json_dict(GUI_CONFIG_PATH)
        self.runtime_cfg = load_json_dict(RUNTIME_CONFIG_PATH)
        validate_gui_config(self.gui_cfg)
        self.camera_configs = [cfg for cfg in load_camera_configs(CAMERA_CONFIG_PATH) if cfg.enabled]
        validate_camera_configs(self.camera_configs)

        self.grid_display_fps = float(self.runtime_cfg.get("grid_display_fps", 10.0))
        self.detail_display_fps = float(self.runtime_cfg.get("detail_display_fps", 15.0))
        self.gui_poll_interval_ms = int(round(1000.0 / max(1.0, self.grid_display_fps)))
        self.detail_poll_interval_ms = int(round(1000.0 / max(1.0, self.detail_display_fps)))
        self.detail_windows = {}
        self.last_detail_poll_ts = {}
        self.last_preview_mtime = {}

        self.setWindowTitle("RTC VISION CCTV MONITOR")
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
            title = self.camera_configs[index].name if index < len(self.camera_configs) else f"Empty {index + 1}"
            tile = ImageTile(index, title, int(self.gui_cfg["cell_min_width"]), int(self.gui_cfg["cell_min_height"]))
            tile.clicked.connect(self.on_tile_clicked)
            self.tiles.append(tile)
            self.grid.addWidget(tile, index // int(self.gui_cfg["grid_cols"]), index % int(self.gui_cfg["grid_cols"]))

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.update_views)
        self.timer.start(self.gui_poll_interval_ms)

    @staticmethod
    def _read_json(path) -> dict | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _read_image(path):
        if not path.exists():
            return None
        return cv2.imread(str(path))

    @staticmethod
    def _coalesce_frame(primary_frame, fallback_frame):
        return primary_frame if primary_frame is not None else fallback_frame

    def on_tile_clicked(self, index: int):
        if index >= len(self.camera_configs):
            return
        camera_cfg = self.camera_configs[index]
        camera_id = camera_cfg.camera_id
        selected = load_selected_cameras()
        selected.add(camera_id)
        save_selected_cameras(selected)

        window = self.detail_windows.get(camera_id)
        if window is None:
            window = DetailWindow(camera_id)
            self.detail_windows[camera_id] = window

        self._update_detail_window(camera_id, window)
        window.show()
        window.raise_()
        window.activateWindow()

    def _update_detail_window(self, camera_id: str, window: DetailWindow) -> None:
        cfg = next((item for item in self.camera_configs if item.camera_id == camera_id), None)
        if cfg is None:
            return
        backend = self._read_json(camera_snapshot_path(camera_id)) or {}
        backend["camera_id"] = camera_id
        backend.setdefault("camera_name", cfg.name)
        backend.setdefault("camera_type", cfg.camera_type)
        backend.setdefault("camera_health", "unknown")
        backend.setdefault("frame_id", -1)
        backend.setdefault("timestamp", 0.0)
        backend.setdefault("detect_ms", 0.0)
        backend.setdefault("current_states", backend.get("zones", []))
        preview_frame = self._read_image(camera_preview_path(camera_id))
        debug_frame = self._read_image(camera_debug_path(camera_id))
        backend["raw_frame"] = self._coalesce_frame(preview_frame, window.origin_panel.last_frame_bgr)
        backend["debug_frame"] = self._coalesce_frame(debug_frame, window.processed_panel.last_frame_bgr)
        window.update_result(backend)

    def update_views(self):
        for index, tile in enumerate(self.tiles):
            if index >= len(self.camera_configs):
                tile.set_empty(f"Empty {index + 1}")
                continue
            camera_cfg = self.camera_configs[index]
            preview_path = camera_preview_path(camera_cfg.camera_id)
            if not preview_path.exists():
                tile.set_title(camera_cfg.name)
                tile.set_frame(None)
                continue
            mtime = preview_path.stat().st_mtime_ns
            if self.last_preview_mtime.get(camera_cfg.camera_id) == mtime:
                continue
            self.last_preview_mtime[camera_cfg.camera_id] = mtime
            tile.set_title(f"{camera_cfg.name} ({camera_cfg.camera_id})")
            frame = self._read_image(preview_path)
            if frame is not None:
                tile.set_frame(frame)

        now_ts = time.time()
        selected = load_selected_cameras()
        changed_selection = False
        for camera_id, window in list(self.detail_windows.items()):
            if not window.isVisible():
                if camera_id in selected:
                    selected.remove(camera_id)
                    changed_selection = True
                continue
            if camera_id not in selected:
                selected.add(camera_id)
                changed_selection = True
            last_ts = self.last_detail_poll_ts.get(camera_id, 0.0)
            if now_ts - last_ts < (self.detail_poll_interval_ms / 1000.0):
                continue
            self._update_detail_window(camera_id, window)
            self.last_detail_poll_ts[camera_id] = now_ts
        if changed_selection:
            save_selected_cameras(selected)

    def closeEvent(self, event):
        selected = load_selected_cameras()
        selected.difference_update(self.detail_windows.keys())
        save_selected_cameras(selected)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    try:
        window = CctvMonitorWindow()
    except ValueError as exc:
        QMessageBox.critical(None, "Config Error", str(exc))
        sys.exit(1)
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
