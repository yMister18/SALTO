from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np


PointInt = Tuple[int, int]
SnapCallback = Callable[[np.ndarray, PointInt], PointInt]


@dataclass(frozen=True)
class PointSelectionResult:
    clicked_point: PointInt
    final_point: PointInt


class PointSelectionCancelled(RuntimeError):
    pass


class CalibrationCancelled(RuntimeError):
    pass


class CalibrationUI:
    """
    Recolha manual de pontos de calibração sobre um frame.

    Controlo:
    - Clique esquerdo: adicionar ponto
    - BACKSPACE / DELETE: remover último ponto
    - ENTER: confirmar quando tiver os pontos necessários
    - ESC: cancelar
    """

    def __init__(
        self,
        window_name: str = "LAP2GO - Calibration",
        max_preview_width: int = 1800,
        max_preview_height: int = 1000,
    ) -> None:
        self.window_name = window_name
        self.max_preview_width = max_preview_width
        self.max_preview_height = max_preview_height
        self._frame: Optional[np.ndarray] = None
        self._points: List[PointInt] = []

    def collect_points(
        self,
        frame: np.ndarray,
        required_points: int = 4,
    ) -> List[PointInt]:
        if required_points < 4:
            raise ValueError("required_points deve ser >= 4.")

        self._frame = frame.copy()
        self._points = []

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        while True:
            canvas = self._render_calibration_view(required_points)
            cv2.imshow(self.window_name, canvas)
            key = cv2.waitKeyEx(20)

            if key in (13, 10):
                if len(self._points) == required_points:
                    cv2.destroyWindow(self.window_name)
                    return list(self._points)
            elif key in (8, 127):
                if self._points:
                    self._points.pop()
            elif key == 27:
                cv2.destroyWindow(self.window_name)
                raise CalibrationCancelled("Calibração cancelada pelo utilizador.")

    def _mouse_callback(self, event, x, y, flags, param) -> None:
        if event != cv2.EVENT_LBUTTONDOWN or self._frame is None:
            return

        display_frame, scale = self._fit_for_preview(self._frame)
        original_x = int(round(x / scale))
        original_y = int(round(y / scale))

        height, width = self._frame.shape[:2]
        original_x = max(0, min(width - 1, original_x))
        original_y = max(0, min(height - 1, original_y))

        self._points.append((original_x, original_y))

    def _render_calibration_view(self, required_points: int) -> np.ndarray:
        assert self._frame is not None
        preview, scale = self._fit_for_preview(self._frame.copy())

        for idx, (px, py) in enumerate(self._points, start=1):
            dx = int(round(px * scale))
            dy = int(round(py * scale))
            cv2.circle(preview, (dx, dy), 8, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.putText(
                preview,
                str(idx),
                (dx + 12, dy - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

        overlay = preview.copy()
        cv2.rectangle(overlay, (10, 10), (preview.shape[1] - 10, 110), (0, 0, 0), -1)
        preview = cv2.addWeighted(overlay, 0.45, preview, 0.55, 0)

        lines = [
            f"Selecione {required_points} pontos de calibração ({len(self._points)}/{required_points})",
            "Clique esquerdo: adicionar ponto | BACKSPACE: apagar último",
            "ENTER: confirmar | ESC: cancelar",
        ]

        y = 38
        for line in lines:
            cv2.putText(
                preview,
                line,
                (24, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            y += 28

        return preview

    def _fit_for_preview(self, frame: np.ndarray) -> tuple[np.ndarray, float]:
        height, width = frame.shape[:2]
        scale = min(
            self.max_preview_width / width,
            self.max_preview_height / height,
            1.0,
        )
        if scale < 1.0:
            preview = cv2.resize(
                frame,
                (int(width * scale), int(height * scale)),
                interpolation=cv2.INTER_AREA,
            )
            return preview, scale
        return frame, 1.0


class ZoomPointSelector:
    """
    Seleção precisa do ponto de impacto sobre frame full resolution.

    Controlo:
    - Clique esquerdo: selecionar ponto manual
    - Arrastar ponto final com botão esquerdo perto do marcador vermelho
    - +/-: zoom in/out
    - Setas: pan
    - R: recentrar na seleção
    - S: reaplicar snap ao ponto clicado
    - C: usar ponto clicado como ponto final
    - ENTER: confirmar
    - ESC: cancelar

    Regras:
    - clicked_point = clique bruto do operador
    - final_point = ponto final ajustado, podendo ser snap ou correção manual
    """

    def __init__(
        self,
        window_name: str = "LAP2GO - Impact Point Selector",
        viewport_width: int = 1600,
        viewport_height: int = 900,
        min_zoom: float = 1.0,
        max_zoom: float = 12.0,
        pan_step_px: int = 80,
        drag_activation_radius_px: int = 16,
    ) -> None:
        self.window_name = window_name
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom
        self.pan_step_px = pan_step_px
        self.drag_activation_radius_px = drag_activation_radius_px

        self._image: Optional[np.ndarray] = None
        self._clicked_point: Optional[PointInt] = None
        self._final_point: Optional[PointInt] = None
        self._snap_callback: Optional[SnapCallback] = None

        self._zoom: float = 1.0
        self._view_x: int = 0
        self._view_y: int = 0
        self._dragging_final_point: bool = False

    def select_point(
        self,
        frame: np.ndarray,
        snap_callback: Optional[SnapCallback] = None,
        initial_point: Optional[PointInt] = None,
    ) -> PointSelectionResult:
        self._image = frame.copy()
        self._snap_callback = snap_callback
        self._clicked_point = initial_point
        self._final_point = initial_point
        self._zoom = 1.0
        self._view_x = 0
        self._view_y = 0
        self._dragging_final_point = False

        if initial_point is not None:
            self._center_on_point(initial_point)

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.viewport_width, self.viewport_height + 100)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        while True:
            canvas = self._render()
            cv2.imshow(self.window_name, canvas)
            key = cv2.waitKeyEx(20)

            if key in (13, 10):
                if self._clicked_point is not None and self._final_point is not None:
                    cv2.destroyWindow(self.window_name)
                    return PointSelectionResult(
                        clicked_point=self._clicked_point,
                        final_point=self._final_point,
                    )
            elif key == 27:
                cv2.destroyWindow(self.window_name)
                raise PointSelectionCancelled("Seleção do ponto cancelada pelo utilizador.")
            elif key in (ord("+"), ord("=")):
                self._change_zoom(1.25)
            elif key in (ord("-"), ord("_")):
                self._change_zoom(1 / 1.25)
            elif key in (81, 2424832):
                self._pan(-self.pan_step_px, 0)
            elif key in (83, 2555904):
                self._pan(self.pan_step_px, 0)
            elif key in (82, 2490368):
                self._pan(0, -self.pan_step_px)
            elif key in (84, 2621440):
                self._pan(0, self.pan_step_px)
            elif key in (ord("r"), ord("R")):
                if self._final_point is not None:
                    self._center_on_point(self._final_point)
            elif key in (ord("s"), ord("S")):
                self._reapply_snap()
            elif key in (ord("c"), ord("C")):
                if self._clicked_point is not None:
                    self._final_point = self._clicked_point

    def _mouse_callback(self, event, x, y, flags, param) -> None:
        if self._image is None:
            return

        image_h, image_w = self._image.shape[:2]
        view_w, view_h = self._current_view_size()
        display_h = int(view_h * self._zoom)
        if y >= display_h:
            return

        img_x, img_y = self._screen_to_image(x, y)
        img_x = max(0, min(image_w - 1, img_x))
        img_y = max(0, min(image_h - 1, img_y))
        current = (img_x, img_y)

        if event == cv2.EVENT_LBUTTONDOWN:
            if self._final_point is not None:
                fx, fy = self._final_point
                dx = fx - img_x
                dy = fy - img_y
                if (dx * dx + dy * dy) ** 0.5 <= self.drag_activation_radius_px / self._zoom:
                    self._dragging_final_point = True
                    return

            self._clicked_point = current
            self._final_point = self._apply_snap(current)
            self._center_on_point(self._final_point)

        elif event == cv2.EVENT_MOUSEMOVE:
            if self._dragging_final_point:
                self._final_point = current

        elif event == cv2.EVENT_LBUTTONUP:
            self._dragging_final_point = False

    def _apply_snap(self, point: PointInt) -> PointInt:
        if self._image is None or self._snap_callback is None:
            return point
        snapped = self._snap_callback(self._image, point)
        return self._clamp_point(snapped)

    def _reapply_snap(self) -> None:
        if self._clicked_point is None:
            return
        self._final_point = self._apply_snap(self._clicked_point)
        self._center_on_point(self._final_point)

    def _change_zoom(self, factor: float) -> None:
        if self._image is None:
            return

        old_zoom = self._zoom
        new_zoom = max(self.min_zoom, min(self.max_zoom, self._zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-9:
            return

        center_before = self._viewport_center_in_image()
        self._zoom = new_zoom
        self._center_on_point(center_before)

    def _pan(self, dx_screen: int, dy_screen: int) -> None:
        if self._image is None:
            return

        dx_img = int(round(dx_screen / self._zoom))
        dy_img = int(round(dy_screen / self._zoom))
        self._view_x += dx_img
        self._view_y += dy_img
        self._clamp_view()

    def _center_on_point(self, point: PointInt) -> None:
        if self._image is None:
            return

        view_w, view_h = self._current_view_size()
        self._view_x = int(round(point[0] - view_w / 2))
        self._view_y = int(round(point[1] - view_h / 2))
        self._clamp_view()

    def _viewport_center_in_image(self) -> PointInt:
        view_w, view_h = self._current_view_size()
        return self._clamp_point((self._view_x + view_w // 2, self._view_y + view_h // 2))

    def _current_view_size(self) -> tuple[int, int]:
        assert self._image is not None
        image_h, image_w = self._image.shape[:2]
        view_w = max(1, min(image_w, int(round(self.viewport_width / self._zoom))))
        view_h = max(1, min(image_h, int(round(self.viewport_height / self._zoom))))
        return view_w, view_h

    def _clamp_view(self) -> None:
        assert self._image is not None
        image_h, image_w = self._image.shape[:2]
        view_w, view_h = self._current_view_size()
        self._view_x = max(0, min(self._view_x, image_w - view_w))
        self._view_y = max(0, min(self._view_y, image_h - view_h))

    def _clamp_point(self, point: PointInt) -> PointInt:
        assert self._image is not None
        image_h, image_w = self._image.shape[:2]
        x = max(0, min(image_w - 1, int(point[0])))
        y = max(0, min(image_h - 1, int(point[1])))
        return x, y

    def _screen_to_image(self, x: int, y: int) -> PointInt:
        img_x = self._view_x + int(round(x / self._zoom))
        img_y = self._view_y + int(round(y / self._zoom))
        return img_x, img_y

    def _render(self) -> np.ndarray:
        assert self._image is not None

        self._clamp_view()
        view_w, view_h = self._current_view_size()

        roi = self._image[
            self._view_y:self._view_y + view_h,
            self._view_x:self._view_x + view_w,
        ].copy()

        canvas = cv2.resize(
            roi,
            (int(view_w * self._zoom), int(view_h * self._zoom)),
            interpolation=cv2.INTER_LINEAR,
        )

        self._draw_crosshair(canvas)
        self._draw_points(canvas)

        info_height = 110
        output = np.zeros((canvas.shape[0] + info_height, canvas.shape[1], 3), dtype=np.uint8)
        output[:canvas.shape[0], :, :] = canvas

        lines = [
            "Clique: selecionar | arrastar marcador vermelho: corrigir",
            "+/-: zoom | setas: mover | R: recentrar | S: snap | C: usar clique bruto",
            "ENTER: confirmar | ESC: cancelar",
            self._status_text(),
        ]

        y = canvas.shape[0] + 26
        for idx, line in enumerate(lines):
            color = (255, 255, 255) if idx < 3 else (120, 255, 120)
            cv2.putText(
                output,
                line,
                (16, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
                cv2.LINE_AA,
            )
            y += 24

        return output

    def _draw_crosshair(self, canvas: np.ndarray) -> None:
        cx = canvas.shape[1] // 2
        cy = canvas.shape[0] // 2
        cv2.line(canvas, (cx - 20, cy), (cx + 20, cy), (255, 255, 255), 1, cv2.LINE_AA)
        cv2.line(canvas, (cx, cy - 20), (cx, cy + 20), (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_points(self, canvas: np.ndarray) -> None:
        if self._clicked_point is not None:
            cx, cy = self._image_to_canvas(self._clicked_point)
            cv2.circle(canvas, (cx, cy), 10, (0, 165, 255), 2, cv2.LINE_AA)

        if self._final_point is not None:
            fx, fy = self._image_to_canvas(self._final_point)
            cv2.circle(canvas, (fx, fy), 7, (0, 0, 255), -1, cv2.LINE_AA)

        if self._clicked_point is not None and self._final_point is not None:
            cx, cy = self._image_to_canvas(self._clicked_point)
            fx, fy = self._image_to_canvas(self._final_point)
            cv2.line(canvas, (cx, cy), (fx, fy), (255, 0, 0), 2, cv2.LINE_AA)

    def _image_to_canvas(self, point: PointInt) -> PointInt:
        x = int(round((point[0] - self._view_x) * self._zoom))
        y = int(round((point[1] - self._view_y) * self._zoom))
        return x, y

    def _status_text(self) -> str:
        clicked = self._clicked_point if self._clicked_point is not None else ("-", "-")
        final = self._final_point if self._final_point is not None else ("-", "-")
        return (
            f"zoom={self._zoom:.2f} "
            f"view=({self._view_x},{self._view_y}) "
            f"clicked={clicked} final={final}"
        )