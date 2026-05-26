from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout


def cv2_frame_to_qpixmap(frame_bgr: np.ndarray) -> QPixmap:
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = frame_rgb.shape
    bytes_per_line = ch * w
    image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
    return QPixmap.fromImage(image.copy())


class PreviewImageLabel(QLabel):
    clicked = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self._pixmap: Optional[QPixmap] = None
        self._display_rect = None

    def set_preview_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self._update_scaled_pixmap()

    def clear_preview(self, text: str) -> None:
        self._pixmap = None
        self._display_rect = None
        self.setPixmap(QPixmap())
        self.setText(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()

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

        image_x = int(round(rel_x * (self._pixmap.width() - 1)))
        image_y = int(round(rel_y * (self._pixmap.height() - 1)))

        image_x = max(0, min(self._pixmap.width() - 1, image_x))
        image_y = max(0, min(self._pixmap.height() - 1, image_y))

        self.clicked.emit(image_x, image_y)

    def _update_scaled_pixmap(self) -> None:
        if self._pixmap is None or self.width() <= 0 or self.height() <= 0:
            return

        scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

        from PySide6.QtCore import QRect
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self._display_rect = QRect(x, y, scaled.width(), scaled.height())


class CameraPreviewWidget(QGroupBox):
    def __init__(self, title: str = "Preview") -> None:
        super().__init__(title)

        self.preview_label = PreviewImageLabel()
        self.preview_label.setMinimumSize(960, 540)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #101010;
                color: #dddddd;
                border: 1px solid #444444;
                font-size: 18px;
            }
        """)
        self.preview_label.setText("Preview multi-câmara indisponível")

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview_label)

    def set_message(self, text: str) -> None:
        self.preview_label.clear_preview(text)

    def set_frame(self, frame_bgr: np.ndarray) -> None:
        if frame_bgr is None or frame_bgr.size == 0:
            self.set_message("Frame inválido")
            return
        pixmap = cv2_frame_to_qpixmap(frame_bgr)
        self.preview_label.setText("")
        self.preview_label.set_preview_pixmap(pixmap)