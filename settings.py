from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path = Path("output")
    calibration_dir: Path = Path("output/calibrations")
    measurements_dir: Path = Path("output/measurements")
    logs_dir: Path = Path("output/logs")


@dataclass(frozen=True)
class CalibrationSettings:
    min_points: int = 4
    max_points: int = 32
    reprojection_error_warning_px: float = 2.5
    reprojection_error_fail_px: float = 8.0


@dataclass(frozen=True)
class MeasurementSettings:
    distance_precision_decimals: int = 2
    default_call_line_world_cm: Tuple[Tuple[float, float], Tuple[float, float]] = (
        (0.0, 0.0),
        (400.0, 0.0),
    )


@dataclass(frozen=True)
class SupportedSandboxLayouts:
    presets_cm: List[Tuple[str, List[Tuple[float, float]]]] = field(
        default_factory=lambda: [
            (
                "default_rect_400x900",
                [(0.0, 0.0), (400.0, 0.0), (400.0, 900.0), (0.0, 900.0)],
            )
        ]
    )


@dataclass(frozen=True)
class AppSettings:
    paths: AppPaths = AppPaths()
    calibration: CalibrationSettings = CalibrationSettings()
    measurement: MeasurementSettings = MeasurementSettings()
    sandbox_layouts: SupportedSandboxLayouts = SupportedSandboxLayouts()


SETTINGS = AppSettings()