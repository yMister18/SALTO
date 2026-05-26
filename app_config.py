from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from camera_manager import CameraSourceConfig


@dataclass(frozen=True)
class AppPathConfig:
    base_dir: str
    calibrations_dir: str
    measurements_dir: str
    logs_dir: str


@dataclass(frozen=True)
class RecordingAppConfig:
    duration_seconds_default: float
    pre_buffer_seconds_default: float
    sync_tolerance_ms: float
    min_required_cameras: int
    poll_interval_seconds: float
    session_fps: int
    video_codec: str
    file_extension: str
    write_timestamp_overlay: bool


@dataclass(frozen=True)
class AnalysisAppConfig:
    default_analysis_camera_id: int
    default_calibration_name: str
    default_call_line_world_cm: tuple[tuple[float, float], tuple[float, float]]
    distance_precision_decimals: int


@dataclass(frozen=True)
class CalibrationPreset:
    name: str
    world_points_cm: list[tuple[float, float]]


@dataclass(frozen=True)
class CalibrationAppConfig:
    min_points: int
    max_points: int
    reprojection_error_warning_px: float
    reprojection_error_fail_px: float
    default_preset_name: str
    presets: list[CalibrationPreset]


@dataclass(frozen=True)
class ApplicationConfig:
    paths: AppPathConfig
    recording: RecordingAppConfig
    analysis: AnalysisAppConfig
    calibration: CalibrationAppConfig
    cameras: list[CameraSourceConfig]


class ConfigError(RuntimeError):
    pass


def load_app_config(path: str | Path = "config.json") -> ApplicationConfig:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Config não encontrado: {source}")

    raw = json.loads(source.read_text(encoding="utf-8"))
    return _parse_application_config(raw)


def _parse_application_config(raw: dict[str, Any]) -> ApplicationConfig:
    try:
        paths = AppPathConfig(**raw["paths"])
        recording = RecordingAppConfig(**raw["recording"])

        analysis_raw = raw["analysis"]
        analysis = AnalysisAppConfig(
            default_analysis_camera_id=int(analysis_raw["default_analysis_camera_id"]),
            default_calibration_name=str(analysis_raw["default_calibration_name"]),
            default_call_line_world_cm=_parse_line_points(
                analysis_raw["default_call_line_world_cm"]
            ),
            distance_precision_decimals=int(analysis_raw["distance_precision_decimals"]),
        )

        calibration_raw = raw["calibration"]
        presets = [
            CalibrationPreset(
                name=str(item["name"]),
                world_points_cm=_parse_points(item["world_points_cm"]),
            )
            for item in calibration_raw["presets"]
        ]
        calibration = CalibrationAppConfig(
            min_points=int(calibration_raw["min_points"]),
            max_points=int(calibration_raw["max_points"]),
            reprojection_error_warning_px=float(
                calibration_raw["reprojection_error_warning_px"]
            ),
            reprojection_error_fail_px=float(
                calibration_raw["reprojection_error_fail_px"]
            ),
            default_preset_name=str(calibration_raw["default_preset_name"]),
            presets=presets,
        )

        cameras = [_parse_camera_config(item) for item in raw["cameras"]]
    except KeyError as exc:
        raise ConfigError(f"Campo obrigatório em falta no config: {exc}") from exc
    except Exception as exc:
        raise ConfigError(f"Erro ao interpretar config: {exc}") from exc

    _validate_config(paths, recording, analysis, calibration, cameras)

    return ApplicationConfig(
        paths=paths,
        recording=recording,
        analysis=analysis,
        calibration=calibration,
        cameras=cameras,
    )


def _parse_camera_config(raw: dict[str, Any]) -> CameraSourceConfig:
    source_type = raw["source_type"]
    if source_type not in {"usb", "rtsp", "video_file"}:
        raise ConfigError(f"source_type inválido: {source_type}")

    source_value: str | int = raw["source"]
    if source_type == "usb":
        source_value = int(source_value)
    else:
        source_value = str(source_value)

    return CameraSourceConfig(
        camera_id=int(raw["camera_id"]),
        name=str(raw["name"]),
        source_type=source_type,
        source=source_value,
        enabled=bool(raw.get("enabled", True)),
        width=int(raw.get("width", 3840)),
        height=int(raw.get("height", 2160)),
        fps=int(raw.get("fps", 30)),
        buffer_seconds=int(raw.get("buffer_seconds", 8)),
        fourcc=str(raw.get("fourcc", "MJPG")),
        warmup_seconds=float(raw.get("warmup_seconds", 1.0)),
        open_timeout_seconds=float(raw.get("open_timeout_seconds", 5.0)),
        read_retry_sleep_seconds=float(raw.get("read_retry_sleep_seconds", 0.01)),
        drop_frames_if_behind=bool(raw.get("drop_frames_if_behind", True)),
    )


def _parse_points(raw_points: list[list[float]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for item in raw_points:
        if len(item) != 2:
            raise ConfigError(f"Ponto inválido: {item}")
        points.append((float(item[0]), float(item[1])))
    return points


def _parse_line_points(raw_points: list[list[float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    points = _parse_points(raw_points)
    if len(points) != 2:
        raise ConfigError("A linha de chamada deve ter exatamente 2 pontos.")
    return points[0], points[1]


def _validate_config(
    paths: AppPathConfig,
    recording: RecordingAppConfig,
    analysis: AnalysisAppConfig,
    calibration: CalibrationAppConfig,
    cameras: list[CameraSourceConfig],
) -> None:
    if not cameras:
        raise ConfigError("O config deve conter pelo menos uma câmara.")

    enabled_cameras = [cam for cam in cameras if cam.enabled]
    if not enabled_cameras:
        raise ConfigError("Tem de existir pelo menos uma câmara ativa.")

    camera_ids = [cam.camera_id for cam in cameras]
    if len(set(camera_ids)) != len(camera_ids):
        raise ConfigError("Existem camera_id duplicados no config.")

    if analysis.default_analysis_camera_id not in [cam.camera_id for cam in enabled_cameras]:
        raise ConfigError(
            "default_analysis_camera_id não corresponde a nenhuma câmara ativa."
        )

    if recording.duration_seconds_default <= 0:
        raise ConfigError("duration_seconds_default deve ser > 0.")
    if recording.pre_buffer_seconds_default < 0:
        raise ConfigError("pre_buffer_seconds_default deve ser >= 0.")
    if recording.session_fps <= 0:
        raise ConfigError("session_fps deve ser > 0.")

    if calibration.min_points < 4:
        raise ConfigError("calibration.min_points deve ser >= 4.")
    if calibration.max_points < calibration.min_points:
        raise ConfigError("calibration.max_points deve ser >= min_points.")

    preset_names = [preset.name for preset in calibration.presets]
    if calibration.default_preset_name not in preset_names:
        raise ConfigError("default_preset_name não existe na lista de presets.")

    if analysis.distance_precision_decimals < 0:
        raise ConfigError("distance_precision_decimals deve ser >= 0.")

    for name, path in {
        "base_dir": paths.base_dir,
        "calibrations_dir": paths.calibrations_dir,
        "measurements_dir": paths.measurements_dir,
        "logs_dir": paths.logs_dir,
    }.items():
        if not str(path).strip():
            raise ConfigError(f"{name} não pode estar vazio.")