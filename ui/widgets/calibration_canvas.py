from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel

from ui.panels.preview_panel import cv2_frame_to_qpixmap


class CalibrationCanvas(QLabel):
    point_added = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(1000, 600)
        self.setStyleSheet("""
            QLabel {
                background-color: #101010;
                border: 1px solid #444444;
            }
        """)
        self._base_image: Optional[np.ndarray] = None
        self._image_width = 0
        self._image_height = 0
        self._pixmap = None
        self._display_rect = None
        self._points: list[tuple[int, int]] = []

    def set_image(self, frame_bgr: np.ndarray) -> None:
        self._base_image = frame_bgr.copy()
        self._image_height, self._image_width = self._base_image.shape[:2]
        self._points = []
        self._pixmap = cv2_frame_to_qpixmap(self._draw_points_overlay())
        self._update_scaled()

    def set_points(self, points: list[tuple[int, int]]) -> None:
        self._points = list(points)
        if self._base_image is not None:
            self._pixmap = cv2_frame_to_qpixmap(self._draw_points_overlay())
            self._update_scaled()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton or self._pixmap is None or self._display_rect is None:
            return

        x = int(event.position().x())
        y = int(event.position().y())
        rect = self._display_rect
        if not rect.contains(x, y):
            return

        rel_x = (x - rect.x()) / max(1, rect.width())
        rel_y = (y - rect.y()) / max(1, rect.height())

        image_x = int(round(rel_x * (self._image_width - 1)))
        image_y = int(round(rel_y * (self._image_height - 1)))

        image_x = max(0, min(self._image_width - 1, image_x))
        image_y = max(0, min(self._image_height - 1, image_y))

        self.point_added.emit(image_x, image_y)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scaled()

    def _draw_points_overlay(self) -> np.ndarray:
        assert self._base_image is not None
        frame = self._base_image.copy()

        for idx, (x, y) in enumerate(self._points, start=1):
            cv2.circle(frame, (x, y), 8, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.putText(
                frame,
                str(idx),
                (x + 12, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

        cv2.rectangle(frame, (10, 10), (980, 60), (0, 0, 0), -1)
        cv2.putText(
            frame,
            "Clique para adicionar pontos de calibração",
            (24, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return frame

    def _update_scaled(self) -> None:
        if self._pixmap is None or self.width() <= 0 or self.height() <= 0:
            return

        scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

        from PySide6.QtCore import QRect
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self._display_rect = QRect(x, y, scaled.width(), scaled.height())