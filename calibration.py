from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import cv2
import numpy as np

from geometry import Line2D, Point2D, perpendicular_distance_to_line
from settings import SETTINGS


@dataclass(frozen=True)
class CalibrationQuality:
    point_count: int
    mean_reprojection_error_px: float
    max_reprojection_error_px: float
    passed: bool
    warning: bool


@dataclass(frozen=True)
class CalibrationData:
    sandbox_name: str
    image_points: List[List[float]]
    world_points_cm: List[List[float]]
    homography: List[List[float]]
    inverse_homography: List[List[float]]
    reprojection_errors_px: List[float]
    quality: CalibrationQuality


class CalibrationError(RuntimeError):
    pass


class CalibrationValidationError(CalibrationError):
    pass


class CalibrationManager:
    def __init__(self) -> None:
        self._H: np.ndarray | None = None
        self._H_inv: np.ndarray | None = None
        self._data: CalibrationData | None = None

    @property
    def is_ready(self) -> bool:
        return self._H is not None and self._H_inv is not None

    @property
    def data(self) -> CalibrationData:
        if self._data is None:
            raise CalibrationError("Calibração ainda não carregada.")
        return self._data

    def calibrate(
        self,
        image_points: Sequence[Point2D],
        world_points_cm: Sequence[Point2D],
        sandbox_name: str = "default",
    ) -> CalibrationData:
        self._validate_input_points(image_points, world_points_cm)

        img = np.array(image_points, dtype=np.float64)
        wrd = np.array(world_points_cm, dtype=np.float64)

        H, mask = cv2.findHomography(img, wrd, method=0)
        if H is None:
            raise CalibrationError("Falha ao calcular a homografia.")

        H_inv = np.linalg.inv(H)
        reprojection_errors = self._compute_reprojection_errors(img, wrd, H)
        quality = self._evaluate_quality(reprojection_errors)

        if not quality.passed:
            raise CalibrationValidationError(
                f"Calibração rejeitada. erro_médio={quality.mean_reprojection_error_px:.3f}px "
                f"erro_máximo={quality.max_reprojection_error_px:.3f}px"
            )

        data = CalibrationData(
            sandbox_name=sandbox_name,
            image_points=[[float(x), float(y)] for x, y in image_points],
            world_points_cm=[[float(x), float(y)] for x, y in world_points_cm],
            homography=H.tolist(),
            inverse_homography=H_inv.tolist(),
            reprojection_errors_px=[float(v) for v in reprojection_errors],
            quality=quality,
        )

        self._H = H
        self._H_inv = H_inv
        self._data = data
        return data

    def save(self, calibration_data: CalibrationData, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = asdict(calibration_data)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load(self, path: str | Path) -> CalibrationData:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"Ficheiro de calibração não encontrado: {source}")

        raw = json.loads(source.read_text(encoding="utf-8"))
        quality = CalibrationQuality(**raw["quality"])
        data = CalibrationData(
            sandbox_name=raw["sandbox_name"],
            image_points=raw["image_points"],
            world_points_cm=raw["world_points_cm"],
            homography=raw["homography"],
            inverse_homography=raw["inverse_homography"],
            reprojection_errors_px=raw["reprojection_errors_px"],
            quality=quality,
        )

        self._H = np.array(data.homography, dtype=np.float64)
        self._H_inv = np.array(data.inverse_homography, dtype=np.float64)
        self._data = data
        return data

    def image_to_world(self, point_xy: Point2D) -> Point2D:
        if self._H is None:
            raise CalibrationError("Homografia não disponível.")
        pt = np.array([[[point_xy[0], point_xy[1]]]], dtype=np.float64)
        dst = cv2.perspectiveTransform(pt, self._H)[0][0]
        return float(dst[0]), float(dst[1])

    def world_to_image(self, point_xy_cm: Point2D) -> Point2D:
        if self._H_inv is None:
            raise CalibrationError("Homografia inversa não disponível.")
        pt = np.array([[[point_xy_cm[0], point_xy_cm[1]]]], dtype=np.float64)
        dst = cv2.perspectiveTransform(pt, self._H_inv)[0][0]
        return float(dst[0]), float(dst[1])

    def transform_image_points_to_world(
        self,
        points_xy: Iterable[Point2D],
    ) -> list[Point2D]:
        return [self.image_to_world(p) for p in points_xy]

    def measure_perpendicular_distance_cm(
        self,
        image_point_xy: Point2D,
        call_line_world_cm: Line2D,
    ) -> float:
        world_point = self.image_to_world(image_point_xy)
        return perpendicular_distance_to_line(world_point, call_line_world_cm)

    def _validate_input_points(
        self,
        image_points: Sequence[Point2D],
        world_points_cm: Sequence[Point2D],
    ) -> None:
        if len(image_points) != len(world_points_cm):
            raise CalibrationValidationError(
                "O número de image_points tem de coincidir com world_points_cm."
            )

        if len(image_points) < SETTINGS.calibration.min_points:
            raise CalibrationValidationError(
                f"São necessários pelo menos {SETTINGS.calibration.min_points} pontos."
            )

        if len(image_points) > SETTINGS.calibration.max_points:
            raise CalibrationValidationError(
                f"São permitidos no máximo {SETTINGS.calibration.max_points} pontos."
            )

        if len(set(image_points)) < 4 or len(set(world_points_cm)) < 4:
            raise CalibrationValidationError(
                "Os pontos de calibração devem conter pelo menos 4 pontos distintos."
            )

    def _compute_reprojection_errors(
        self,
        image_points: np.ndarray,
        world_points_cm: np.ndarray,
        H: np.ndarray,
    ) -> np.ndarray:
        H_inv = np.linalg.inv(H)
        projected_back = cv2.perspectiveTransform(
            world_points_cm.reshape(-1, 1, 2).astype(np.float64),
            H_inv,
        ).reshape(-1, 2)

        diffs = projected_back - image_points
        return np.linalg.norm(diffs, axis=1)

    def _evaluate_quality(self, reprojection_errors: np.ndarray) -> CalibrationQuality:
        mean_err = float(np.mean(reprojection_errors))
        max_err = float(np.max(reprojection_errors))
        warning = mean_err > SETTINGS.calibration.reprojection_error_warning_px
        passed = max_err <= SETTINGS.calibration.reprojection_error_fail_px

        return CalibrationQuality(
            point_count=int(len(reprojection_errors)),
            mean_reprojection_error_px=mean_err,
            max_reprojection_error_px=max_err,
            passed=passed,
            warning=warning,
        )