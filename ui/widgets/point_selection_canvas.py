from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel

from ui.panels.preview_panel import cv2_frame_to_qpixmap


class PointSelectionCanvas(QLabel):
    point_clicked = Signal(int, int)
    point_dragged = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(1100, 700)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: #101010;
                border: 1px solid #444444;
            }
        """)
        self._base_image: Optional[np.ndarray] = None
        self._display_rect = None
        self._image_w = 0
        self._image_h = 0
        self._zoom = 1.0
        self._min_zoom = 1.0
        self._max_zoom = 8.0
        self._view_x = 0
        self._view_y = 0
        self._clicked_point: Optional[tuple[int, int]] = None
        self._final_point: Optional[tuple[int, int]] = None
        self._dragging_final = False

    def set_image(self, frame_bgr: np.ndarray) -> None:
        self._base_image = frame_bgr.copy()
        self._image_h, self._image_w = self._base_image.shape[:2]
        self._zoom = 1.0
        self._view_x = 0
        self._view_y = 0
        self._clicked_point = None
        self._final_point = None
        self._render()

    def set_points(self, clicked_point: Optional[tuple[int, int]], final_point: Optional[tuple[int, int]]) -> None:
        self._clicked_point = clicked_point
        self._final_point = final_point
        self._render()

    def zoom_in(self) -> None:
        self._set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self._set_zoom(self._zoom / 1.25)

    def pan(self, dx: int, dy: int) -> None:
        if self._base_image is None:
            return
        self._view_x += int(round(dx / self._zoom))
        self._view_y += int(round(dy / self._zoom))
        self._clamp_view()
        self._render()

    def center_on_point(self, point: tuple[int, int]) -> None:
        if self._base_image is None:
            return
        view_w, view_h = self._current_view_size()
        self._view_x = int(round(point[0] - view_w / 2))
        self._view_y = int(round(point[1] - view_h / 2))
        self._clamp_view()
        self._render()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._base_image is None or self._display_rect is None:
            return
        if event.button() != Qt.LeftButton:
            return

        pt = self._screen_to_image(int(event.position().x()), int(event.position().y()))
        if pt is None:
            return

        if self._final_point is not None:
            dist = ((pt[0] - self._final_point[0]) ** 2 + (pt[1] - self._final_point[1]) ** 2) ** 0.5
            if dist <= (18 / self._zoom):
                self._dragging_final = True
                return

        self.point_clicked.emit(pt[0], pt[1])

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging_final:
            return
        pt = self._screen_to_image(int(event.position().x()), int(event.position().y()))
        if pt is None:
            return
        self.point_dragged.emit(pt[0], pt[1])

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging_final = False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render()

    def _set_zoom(self, zoom: float) -> None:
        if self._base_image is None:
            return
        self._zoom = max(self._min_zoom, min(self._max_zoom, zoom))
        self._clamp_view()
        self._render()

    def _current_view_size(self) -> tuple[int, int]:
        view_w = max(1, min(self._image_w, int(round(self.width() / self._zoom))))
        view_h = max(1, min(self._image_h, int(round(self.height() / self._zoom))))
        return view_w, view_h

    def _clamp_view(self) -> None:
        if self._base_image is None:
            return
        view_w, view_h = self._current_view_size()
        self._view_x = max(0, min(self._view_x, self._image_w - view_w))
        self._view_y = max(0, min(self._view_y, self._image_h - view_h))

    def _render(self) -> None:
        if self._base_image is None or self.width() <= 0 or self.height() <= 0:
            return

        self._clamp_view()
        view_w, view_h = self._current_view_size()

        roi = self._base_image[self._view_y:self._view_y + view_h, self._view_x:self._view_x + view_w].copy()

        canvas = cv2.resize(
            roi,
            (max(1, int(view_w * self._zoom)), max(1, int(view_h * self._zoom))),
            interpolation=cv2.INTER_LINEAR,
        )

        if self._clicked_point is not None:
            x, y = self._image_to_canvas(self._clicked_point)
            cv2.circle(canvas, (x, y), 12, (0, 165, 255), 2, cv2.LINE_AA)

        if self._final_point is not None:
            x, y = self._image_to_canvas(self._final_point)
            cv2.circle(canvas, (x, y), 8, (0, 0, 255), -1, cv2.LINE_AA)

        if self._clicked_point is not None and self._final_point is not None:
            x1, y1 = self._image_to_canvas(self._clicked_point)
            x2, y2 = self._image_to_canvas(self._final_point)
            cv2.line(canvas, (x1, y1), (x2, y2), (255, 0, 0), 2, cv2.LINE_AA)

        cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 90), (0, 0, 0), -1)
        cv2.putText(canvas, f"zoom={self._zoom:.2f} view=({self._view_x},{self._view_y})", (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, "Clique: ponto bruto | arrastar marcador vermelho: corrigir", (20, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 255, 200), 2, cv2.LINE_AA)

        pixmap = cv2_frame_to_qpixmap(canvas)
        scaled = pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

        from PySide6.QtCore import QRect
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self._display_rect = QRect(x, y, scaled.width(), scaled.height())

    def _screen_to_image(self, sx: int, sy: int) -> Optional[tuple[int, int]]:
        if self._display_rect is None or self._base_image is None:
            return None
        rect = self._display_rect
        if not rect.contains(sx, sy):
            return None

        rel_x = (sx - rect.x()) / max(1, rect.width())
        rel_y = (sy - rect.y()) / max(1, rect.height())

        view_w, view_h = self._current_view_size()
        x = self._view_x + int(round(rel_x * (view_w - 1)))
        y = self._view_y + int(round(rel_y * (view_h - 1)))

        x = max(0, min(self._image_w - 1, x))
        y = max(0, min(self._image_h - 1, y))
        return x, y

    def _image_to_canvas(self, pt: tuple[int, int]) -> tuple[int, int]:
        x = int(round((pt[0] - self._view_x) * self._zoom))
        y = int(round((pt[1] - self._view_y) * self._zoom))
        return x, y