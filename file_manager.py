from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np

from settings import SETTINGS


@dataclass(frozen=True)
class AthleteData:
    athlete_name: str
    bib_number: str


@dataclass(frozen=True)
class MeasurementRecord:
    attempt_id: str
    athlete_name: str
    bib_number: str
    camera_id: int
    frame_index: int
    timestamp_iso: str
    clicked_point_px: tuple[int, int]
    snapped_point_px: tuple[int, int]
    world_point_cm: tuple[float, float]
    distance_cm: float
    calibration_file: str
    original_frame_file: str
    annotated_frame_file: str


class FileManager:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else SETTINGS.paths.base_dir
        self.calibration_dir = self.base_dir / "calibrations"
        self.measurements_dir = self.base_dir / "measurements"
        self.logs_dir = self.base_dir / "logs"

        for directory in (
            self.base_dir,
            self.calibration_dir,
            self.measurements_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def create_attempt_dir(self, athlete_name: str, bib_number: str) -> Path:
        attempt_id = self.build_attempt_id(athlete_name, bib_number)
        attempt_dir = self.measurements_dir / attempt_id
        attempt_dir.mkdir(parents=True, exist_ok=True)
        return attempt_dir

    def build_attempt_id(self, athlete_name: str, bib_number: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_athlete = self.slugify(athlete_name)
        safe_bib = self.slugify(bib_number)
        return f"{now}_{safe_athlete}_{safe_bib}"

    def athlete_history_path(self, athlete_name: str, bib_number: str) -> Path:
        return self.measurements_dir / f"athlete_{self.slugify(athlete_name)}_{self.slugify(bib_number)}.json"

    def save_image(self, path: str | Path, image: np.ndarray) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        ok = cv2.imwrite(str(target), image)
        if not ok:
            raise RuntimeError(f"Falha ao gravar imagem: {target}")
        return target

    def save_json(self, path: str | Path, data: Any) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = self._normalize(data)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return target

    def append_csv(self, path: str | Path, rows: Iterable[MeasurementRecord]) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        rows = list(rows)
        if not rows:
            return target

        fieldnames = list(asdict(rows[0]).keys())
        write_header = not target.exists()

        with target.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))
        return target

    def measurement_csv_path(self) -> Path:
        return self.measurements_dir / "measurements.csv"

    def calibration_path(self, calibration_name: str) -> Path:
        return self.calibration_dir / f"{self.slugify(calibration_name)}.json"

    def utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def slugify(self, text: str) -> str:
        normalized = "".join(ch if ch.isalnum() else "_" for ch in text.strip())
        normalized = "_".join(filter(None, normalized.split("_")))
        return normalized or "unknown"

    def _normalize(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._normalize(asdict(value))
        if isinstance(value, dict):
            return {str(k): self._normalize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._normalize(v) for v in value]
        return value