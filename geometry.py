from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

import numpy as np


Point2D = Tuple[float, float]


@dataclass(frozen=True)
class Line2D:
    p1: Point2D
    p2: Point2D

    def as_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        a = np.array(self.p1, dtype=np.float64)
        b = np.array(self.p2, dtype=np.float64)
        return a, b

    def direction(self) -> np.ndarray:
        a, b = self.as_arrays()
        d = b - a
        n = np.linalg.norm(d)
        if n == 0:
            raise ValueError("A linha tem comprimento zero.")
        return d / n

    def normal_left(self) -> np.ndarray:
        d = self.direction()
        return np.array([-d[1], d[0]], dtype=np.float64)


def as_point_array(point: Point2D) -> np.ndarray:
    return np.array(point, dtype=np.float64)


def euclidean_distance(a: Point2D, b: Point2D) -> float:
    pa = as_point_array(a)
    pb = as_point_array(b)
    return float(np.linalg.norm(pa - pb))


def perpendicular_distance_to_line(point: Point2D, line: Line2D) -> float:
    p = as_point_array(point)
    a, b = line.as_arrays()
    ab = b - a
    norm_ab = np.linalg.norm(ab)
    if norm_ab == 0:
        raise ValueError("A linha de referência não pode ter comprimento zero.")

    ap = p - a
    cross_value = ab[0] * ap[1] - ab[1] * ap[0]
    return float(abs(cross_value) / norm_ab)


def signed_distance_to_line(point: Point2D, line: Line2D) -> float:
    p = as_point_array(point)
    a, _ = line.as_arrays()
    normal = line.normal_left()
    return float(np.dot(p - a, normal))


def orthogonal_projection_on_line(point: Point2D, line: Line2D) -> Point2D:
    p = as_point_array(point)
    a, b = line.as_arrays()
    ab = b - a
    denom = np.dot(ab, ab)
    if denom == 0:
        raise ValueError("A linha de referência não pode ter comprimento zero.")
    t = np.dot(p - a, ab) / denom
    proj = a + t * ab
    return float(proj[0]), float(proj[1])


def polyline_length(points: Iterable[Point2D]) -> float:
    pts = list(points)
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for i in range(1, len(pts)):
        total += euclidean_distance(pts[i - 1], pts[i])
    return total