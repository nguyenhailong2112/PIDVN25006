import cv2
from types import SimpleNamespace
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from core.path_utils import PROJECT_ROOT

APP_ICON_PATH = PROJECT_ROOT / "assets" / "rtc_logo.png"


class ImagePanel(QLabel):
    def __init__(self, title: str):
        super().__init__()
        self.panel_title = title
        self.last_frame_bgr = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: black; color: #a0a0a0; border: 1px solid #333333;")
        self.setText(title)
        self.setMinimumSize(640, 360)
        self.setScaledContents(False)

    def set_frame(self, frame_bgr):
        self.last_frame_bgr = frame_bgr
        self._render()

    def _render(self):
        if self.last_frame_bgr is None:
            self.clear()
            self.setText(self.panel_title)
            return

        frame = self.last_frame_bgr

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape

        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(image)

        self.setPixmap(
            pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()


class ZoneGridCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #17191d; border: 1px solid #2d3138;")
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(8)
        self.zone_labels: dict[str, QLabel] = {}
        self.layout_signature = None

    def clear_grid(self):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.zone_labels = {}

    def update_states(self, states):
        if not states:
            self.clear_grid()
            label = QLabel("No zone-based state available")
            label.setStyleSheet("color: #f0f0f0; font-size: 14px;")
            self.layout.addWidget(label, 0, 0)
            self.layout_signature = None
            return

        ordered = sorted(states, key=lambda s: s.zone_id)
        rows = {}
        for state in ordered:
            row_key = state.zone_id[0]
            rows.setdefault(row_key, []).append(state)

        sorted_row_keys = sorted(rows.keys())
        signature = tuple(
            (row_key, tuple(item.zone_id for item in sorted(rows[row_key], key=lambda s: s.zone_id))) for row_key in
            sorted_row_keys)
        if signature != self.layout_signature:
            self.clear_grid()
            self.layout_signature = signature
        max_cols = 0
        for r, row_key in enumerate(sorted_row_keys):
            row_states = sorted(rows[row_key], key=lambda s: s.zone_id)
            max_cols = max(max_cols, len(row_states))
            for c, state in enumerate(row_states):
                label = self.zone_labels.get(state.zone_id)
                if label is None:
                    label = QLabel()
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    label.setStyleSheet(
                        "color: white; font-size: 16px; font-weight: 700; "
                        "padding: 14px; border: 1px solid #3a3f46;"
                    )
                    self.zone_labels[state.zone_id] = label
                    self.layout.addWidget(label, r, c)

                occupied_since = getattr(state, "occupied_since_text", None)
                occupied_line = f"\nĐặt lúc: {occupied_since}" if state.state == "occupied" and occupied_since else ""
                label.setText(f"{state.zone_id}\n{state.state}{occupied_line}")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                color = "#1f6f43" if state.state == "empty" else "#8a6d1d" if state.state == "unknown" else "#7a1f1f"
                label.setStyleSheet(
                    f"background-color: {color}; color: white; font-size: 16px; font-weight: 700; "
                    "padding: 14px; border: 1px solid #3a3f46;"
                )

        for c in range(max_cols):
            self.layout.setColumnStretch(c, 1)
        for r in range(len(sorted_row_keys)):
            self.layout.setRowStretch(r, 1)


class DetailWindow(QMainWindow):
    def __init__(self, camera_id: str):
        super().__init__()
        self.camera_id = camera_id
        self._last_zone_signature = None
        self.setWindowTitle(f"Camera Detail - {camera_id}")
        self.resize(1650, 920)

        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        central = QWidget()
        self.setCentralWidget(central)

        self.header = QLabel("Camera detail")
        self.header.setStyleSheet(
            "background-color: #111317; color: white; font-weight: 700; padding: 10px 12px;"
        )

        self.origin_panel = ImagePanel("Original View")
        self.processed_panel = ImagePanel("Processed View")

        self.zone_grid = ZoneGridCard()

        image_grid = QGridLayout()
        image_grid.setContentsMargins(0, 0, 0, 0)
        image_grid.setSpacing(8)
        image_grid.addWidget(self.origin_panel, 0, 0)
        image_grid.addWidget(self.processed_panel, 0, 1)
        image_grid.setColumnStretch(0, 1)
        image_grid.setColumnStretch(1, 1)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.header)
        layout.addLayout(image_grid, 2)
        layout.addWidget(self.zone_grid, 1)

    @staticmethod
    def _normalize_states(states):
        normalized = []
        for state in states or []:
            if isinstance(state, dict):
                normalized.append(SimpleNamespace(**state))
            else:
                normalized.append(state)
        return normalized

    def update_result(self, result: dict):
        camera_name = result["camera_name"]
        camera_id = result["camera_id"]
        camera_type = result["camera_type"]

        self.setWindowTitle(f"Camera Detail - {camera_name} ({camera_id})")
        self.header.setText(f"{camera_name} ({camera_id}) - {camera_type}")

        self.origin_panel.set_frame(result.get("raw_frame"))
        self.processed_panel.set_frame(result.get("debug_frame"))

        states = self._normalize_states(result.get("current_states", []))
        signature = tuple((state.zone_id, state.state, getattr(state, "occupied_since_text", None)) for state in
                          sorted(states, key=lambda s: s.zone_id))
        if signature != self._last_zone_signature:
            self.zone_grid.update_states(states)
            self._last_zone_signature = signature
