from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from app_config import ApplicationConfig
from calibration import CalibrationManager
from camera_manager import CameraManager
from database import DatabaseManager
from file_manager import FileManager
from recording_manager import RecordingSession


@dataclass
class AppContext:
    config: ApplicationConfig
    file_manager: FileManager
    calibration_manager: CalibrationManager
    database_manager: DatabaseManager
    camera_manager: Optional[CameraManager] = None


@dataclass
class RuntimeSettings:
    duration_seconds: float
    pre_buffer_seconds: float
    default_calibration_name: str
    distance_precision_decimals: int
    default_call_line_world_cm: tuple[tuple[float, float], tuple[float, float]]


@dataclass
class AttemptRuntimeState:
    athlete_name: str = ""
    bib_number: str = ""
    athlete_db_id: Optional[int] = None
    competition_db_id: Optional[int] = None
    attempt_db_id: Optional[int] = None
    attempt_dir: Optional[Path] = None
    analysis_camera_id: Optional[int] = None
    recording_session: Optional[RecordingSession] = None
    selected_frame_index: Optional[int] = None
    selected_frame_timestamp: Optional[float] = None
    selected_frame_bgr: Optional[np.ndarray] = None
    clicked_point_px: Optional[tuple[int, int]] = None
    final_point_px: Optional[tuple[int, int]] = None
    distance_cm: Optional[float] = None
    measurement_payload: Optional[dict] = None