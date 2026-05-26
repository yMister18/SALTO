from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from calibration import CalibrationManager
from geometry import Line2D, Point2D, orthogonal_projection_on_line, perpendicular_distance_to_line


PointInt = Tuple[int, int]


@dataclass(frozen=True)
class SnapDebugData:
    roi_bounds_xyxy: tuple[int, int, int, int]
    candidate_count: int
    best_score: float
    edge_pixels: int
    threshold_pixels: int
    gradient_max: float


@dataclass(frozen=True)
class SnapResult:
    original_point_px: PointInt
    snapped_point_px: PointInt
    moved_distance_px: float
    world_point_cm: Point2D
    distance_cm: float
    projection_on_call_line_cm: Point2D
    debug: SnapDebugData


@dataclass(frozen=True)
class SnapConfig:
    search_radius_px: int = 36
    gaussian_kernel_size: int = 5
    canny_threshold1: int = 35
    canny_threshold2: int = 120
    min_binary_area_px: int = 6
    max_move_px: float = 40.0
    distance_weight: float = 1.0
    edge_weight: float = 2.2
    gradient_weight: float = 1.3
    darkness_weight: float = 0.8
    local_difference_weight: float = 1.1
    centroid_bias_weight: float = 0.6


class ImpactAnalysisError(RuntimeError):
    pass


class ImpactAnalyzer:
    def __init__(
        self,
        calibration_manager: CalibrationManager,
        snap_config: Optional[SnapConfig] = None,
    ) -> None:
        self.calibration_manager = calibration_manager
        self.snap_config = snap_config or SnapConfig()

    def smart_snap(
        self,
        frame: np.ndarray,
        clicked_point_px: PointInt,
    ) -> PointInt:
        result = self.smart_snap_with_debug(frame, clicked_point_px)
        return result.snapped_point_px

    def smart_snap_with_debug(
        self,
        frame: np.ndarray,
        clicked_point_px: PointInt,
    ) -> SnapResult:
        if frame is None or frame.size == 0:
            raise ImpactAnalysisError("Frame inválido para análise.")

        x, y = clicked_point_px
        h, w = frame.shape[:2]
        radius = self.snap_config.search_radius_px

        x1 = max(0, x - radius)
        y1 = max(0, y - radius)
        x2 = min(w, x + radius + 1)
        y2 = min(h, y + radius + 1)

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            raise ImpactAnalysisError("ROI vazia para análise de snap.")

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(
            gray,
            (self.snap_config.gaussian_kernel_size, self.snap_config.gaussian_kernel_size),
            0,
        )

        edges = cv2.Canny(
            blur,
            self.snap_config.canny_threshold1,
            self.snap_config.canny_threshold2,
        )

        grad_x = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = cv2.magnitude(grad_x, grad_y)

        background = cv2.GaussianBlur(gray, (21, 21), 0)
        local_difference = cv2.absdiff(gray, background)

        _, dark_mask = cv2.threshold(
            blur,
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )

        combined_mask = cv2.bitwise_or(edges, dark_mask)
        combined_mask = self._remove_small_components(
            combined_mask,
            min_area=self.snap_config.min_binary_area_px,
        )

        ys, xs = np.where(combined_mask > 0)
        candidate_count = len(xs)

        if candidate_count == 0:
            snapped = self._fallback_to_local_centroid(gray, clicked_point_px, x1, y1)
            moved = self._distance_px(clicked_point_px, snapped)
            world_point = self.calibration_manager.image_to_world(snapped)
            debug = SnapDebugData(
                roi_bounds_xyxy=(x1, y1, x2, y2),
                candidate_count=0,
                best_score=0.0,
                edge_pixels=int(np.count_nonzero(edges)),
                threshold_pixels=int(np.count_nonzero(dark_mask)),
                gradient_max=float(np.max(grad_mag)) if grad_mag.size else 0.0,
            )
            return SnapResult(
                original_point_px=clicked_point_px,
                snapped_point_px=snapped,
                moved_distance_px=moved,
                world_point_cm=world_point,
                distance_cm=0.0,
                projection_on_call_line_cm=(0.0, 0.0),
                debug=debug,
            )

        click_local = np.array([x - x1, y - y1], dtype=np.float32)
        candidates = np.column_stack([xs, ys]).astype(np.float32)

        centroid_local = self._compute_mask_centroid(combined_mask)
        if centroid_local is None:
            centroid_local = click_local

        scores = self._score_candidates(
            candidates=candidates,
            click_local=click_local,
            centroid_local=centroid_local,
            edge_map=edges,
            gradient_map=grad_mag,
            dark_mask=dark_mask,
            local_difference=local_difference,
        )

        best_idx = int(np.argmax(scores))
        best_local = candidates[best_idx]
        snapped = (int(best_local[0] + x1), int(best_local[1] + y1))

        if self._distance_px(clicked_point_px, snapped) > self.snap_config.max_move_px:
            snapped = self._clamp_move(clicked_point_px, snapped, self.snap_config.max_move_px)

        moved = self._distance_px(clicked_point_px, snapped)
        world_point = self.calibration_manager.image_to_world(snapped)

        debug = SnapDebugData(
            roi_bounds_xyxy=(x1, y1, x2, y2),
            candidate_count=int(candidate_count),
            best_score=float(scores[best_idx]),
            edge_pixels=int(np.count_nonzero(edges)),
            threshold_pixels=int(np.count_nonzero(dark_mask)),
            gradient_max=float(np.max(grad_mag)) if grad_mag.size else 0.0,
        )

        return SnapResult(
            original_point_px=clicked_point_px,
            snapped_point_px=snapped,
            moved_distance_px=moved,
            world_point_cm=world_point,
            distance_cm=0.0,
            projection_on_call_line_cm=(0.0, 0.0),
            debug=debug,
        )

    def compute_measurement(
        self,
        frame: np.ndarray,
        clicked_point_px: PointInt,
        call_line_world: Line2D,
        auto_snap: bool = True,
    ) -> SnapResult:
        snap_result = (
            self.smart_snap_with_debug(frame, clicked_point_px)
            if auto_snap
            else self._build_manual_snap_result(clicked_point_px)
        )

        world_point = self.calibration_manager.image_to_world(snap_result.snapped_point_px)
        distance_cm = perpendicular_distance_to_line(world_point, call_line_world)
        projection = orthogonal_projection_on_line(world_point, call_line_world)

        return SnapResult(
            original_point_px=snap_result.original_point_px,
            snapped_point_px=snap_result.snapped_point_px,
            moved_distance_px=snap_result.moved_distance_px,
            world_point_cm=world_point,
            distance_cm=distance_cm,
            projection_on_call_line_cm=projection,
            debug=snap_result.debug,
        )

    def draw_measurement_overlay(
        self,
        frame: np.ndarray,
        result: SnapResult,
        label: Optional[str] = None,
    ) -> np.ndarray:
        output = frame.copy()

        ox, oy = result.original_point_px
        sx, sy = result.snapped_point_px

        cv2.circle(output, (ox, oy), 12, (0, 165, 255), 2, cv2.LINE_AA)
        cv2.circle(output, (sx, sy), 8, (0, 0, 255), -1, cv2.LINE_AA)
        cv2.line(output, (ox, oy), (sx, sy), (255, 0, 0), 2, cv2.LINE_AA)

        info = label or f"{result.distance_cm:.2f} cm"
        box_w = 520
        box_h = 170
        cv2.rectangle(output, (24, 24), (24 + box_w, 24 + box_h), (0, 0, 0), -1)

        lines = [
            f"Distancia: {result.distance_cm:.2f} cm",
            f"Click: {result.original_point_px}",
            f"Snap: {result.snapped_point_px}",
            f"Move: {result.moved_distance_px:.2f} px",
            f"Candidatos: {result.debug.candidate_count} | Score: {result.debug.best_score:.3f}",
            info,
        ]

        y = 52
        for idx, line in enumerate(lines):
            color = (0, 255, 0) if idx == 0 else (255, 255, 255)
            cv2.putText(
                output,
                line,
                (40, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                color,
                2,
                cv2.LINE_AA,
            )
            y += 24

        x1, y1, x2, y2 = result.debug.roi_bounds_xyxy
        cv2.rectangle(output, (x1, y1), (x2, y2), (255, 255, 0), 2, cv2.LINE_AA)

        return output

    def draw_snap_debug_overlay(
        self,
        frame: np.ndarray,
        clicked_point_px: PointInt,
    ) -> np.ndarray:
        snap = self.smart_snap_with_debug(frame, clicked_point_px)
        return self.draw_measurement_overlay(frame, snap, label="Debug snap")

    def _score_candidates(
        self,
        candidates: np.ndarray,
        click_local: np.ndarray,
        centroid_local: np.ndarray,
        edge_map: np.ndarray,
        gradient_map: np.ndarray,
        dark_mask: np.ndarray,
        local_difference: np.ndarray,
    ) -> np.ndarray:
        xs = candidates[:, 0].astype(np.int32)
        ys = candidates[:, 1].astype(np.int32)

        distance_to_click = np.linalg.norm(candidates - click_local[None, :], axis=1)
        distance_to_centroid = np.linalg.norm(candidates - centroid_local[None, :], axis=1)

        edge_strength = edge_map[ys, xs].astype(np.float32) / 255.0
        dark_strength = dark_mask[ys, xs].astype(np.float32) / 255.0

        gradient_values = gradient_map[ys, xs].astype(np.float32)
        gradient_norm = self._normalize_array(gradient_values)

        local_diff_values = local_difference[ys, xs].astype(np.float32)
        local_diff_norm = self._normalize_array(local_diff_values)

        dist_score = 1.0 / (1.0 + distance_to_click)
        centroid_score = 1.0 / (1.0 + distance_to_centroid)

        score = (
            self.snap_config.distance_weight * dist_score
            + self.snap_config.edge_weight * edge_strength
            + self.snap_config.gradient_weight * gradient_norm
            + self.snap_config.darkness_weight * dark_strength
            + self.snap_config.local_difference_weight * local_diff_norm
            + self.snap_config.centroid_bias_weight * centroid_score
        )
        return score.astype(np.float32)

    def _compute_mask_centroid(self, mask: np.ndarray) -> Optional[np.ndarray]:
        moments = cv2.moments(mask)
        if abs(moments["m00"]) < 1e-9:
            return None
        cx = moments["m10"] / moments["m00"]
        cy = moments["m01"] / moments["m00"]
        return np.array([cx, cy], dtype=np.float32)

    def _remove_small_components(self, binary_mask: np.ndarray, min_area: int) -> np.ndarray:
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
        cleaned = np.zeros_like(binary_mask)

        for label in range(1, num_labels):
            area = stats[label, cv2.CC_STAT_AREA]
            if area >= min_area:
                cleaned[labels == label] = 255

        return cleaned

    def _fallback_to_local_centroid(
        self,
        gray: np.ndarray,
        clicked_point_px: PointInt,
        roi_x: int,
        roi_y: int,
    ) -> PointInt:
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)

        ys, xs = np.where(mag > np.mean(mag))
        if len(xs) == 0:
            return clicked_point_px

        cx = int(np.mean(xs)) + roi_x
        cy = int(np.mean(ys)) + roi_y
        return cx, cy

    def _build_manual_snap_result(self, clicked_point_px: PointInt) -> SnapResult:
        world_point = self.calibration_manager.image_to_world(clicked_point_px)
        return SnapResult(
            original_point_px=clicked_point_px,
            snapped_point_px=clicked_point_px,
            moved_distance_px=0.0,
            world_point_cm=world_point,
            distance_cm=0.0,
            projection_on_call_line_cm=(0.0, 0.0),
            debug=SnapDebugData(
                roi_bounds_xyxy=(clicked_point_px[0], clicked_point_px[1], clicked_point_px[0], clicked_point_px[1]),
                candidate_count=1,
                best_score=0.0,
                edge_pixels=0,
                threshold_pixels=0,
                gradient_max=0.0,
            ),
        )

    def _distance_px(self, a: PointInt, b: PointInt) -> float:
        ax, ay = a
        bx, by = b
        return float(((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5)

    def _clamp_move(self, origin: PointInt, target: PointInt, max_distance: float) -> PointInt:
        ox, oy = origin
        tx, ty = target

        dx = tx - ox
        dy = ty - oy
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= 1e-9:
            return origin

        scale = max_distance / dist
        nx = ox + dx * scale
        ny = oy + dy * scale
        return int(round(nx)), int(round(ny))

    def _normalize_array(self, values: np.ndarray) -> np.ndarray:
        if values.size == 0:
            return values.astype(np.float32)
        min_v = float(np.min(values))
        max_v = float(np.max(values))
        if abs(max_v - min_v) < 1e-9:
            return np.ones_like(values, dtype=np.float32)
        return ((values - min_v) / (max_v - min_v)).astype(np.float32)