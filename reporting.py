from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AttemptArtifactManifest:
    attempt_id: str
    attempt_dir: str
    files: dict[str, str]
    videos: dict[str, str]


@dataclass(frozen=True)
class AthleteHistoryEntry:
    attempt_id: str
    athlete_name: str
    bib_number: str
    timestamp_iso: str
    distance_cm: float
    measurement_json: str
    annotated_frame_file: str


class ReportingManager:
    def save_manifest(
        self,
        path: str | Path,
        payload: dict[str, Any],
    ) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return target

    def save_attempt_report(
        self,
        path: str | Path,
        report_text: str,
    ) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report_text, encoding="utf-8")
        return target

    def append_athlete_history(
        self,
        path: str | Path,
        entry: dict[str, Any],
    ) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        history: list[dict[str, Any]] = []
        if target.exists():
            try:
                history = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(history, list):
                    history = []
            except Exception:
                history = []

        history.append(entry)
        target.write_text(
            json.dumps(history, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return target

    def build_attempt_report_text(self, payload: dict[str, Any]) -> str:
        athlete_name = payload["athlete_name"]
        bib_number = payload["bib_number"]
        attempt_dir = payload["attempt_dir"]
        analysis_camera_id = payload["analysis_camera_id"]
        frame_index = payload["frame_index"]
        frame_timestamp = payload["frame_timestamp"]
        distance_cm = payload["distance_cm"]
        world_point_cm = payload["world_point_cm"]
        projection = payload["projection_on_call_line_cm"]

        calibration = payload["calibration"]
        image_quality = payload["image_quality"]
        camera_health = payload["camera_health"]
        files = payload["files"]
        videos = payload["videos"]

        lines = [
            "LAP2GO-SALTO — RELATÓRIO TÉCNICO DE TENTATIVA",
            "",
            f"Atleta: {athlete_name}",
            f"Dorsal: {bib_number}",
            f"Diretoria da tentativa: {attempt_dir}",
            "",
            "MEDIÇÃO",
            f"- Câmara de análise: {analysis_camera_id}",
            f"- Frame selecionado: {frame_index}",
            f"- Timestamp do frame: {frame_timestamp}",
            f"- Distância final: {distance_cm:.2f} cm",
            f"- Ponto no mundo (cm): {world_point_cm}",
            f"- Projeção na linha de chamada (cm): {projection}",
            "",
            "CALIBRAÇÃO",
            f"- Ficheiro: {calibration['file']}",
            f"- Sandbox: {calibration['sandbox_name']}",
            f"- Qualidade: {calibration['quality']}",
            "",
            "QUALIDADE DE IMAGEM",
            f"- Sharpness variance: {image_quality['sharpness_variance']:.2f}",
            f"- Contrast std: {image_quality['contrast_std']:.2f}",
            f"- Brightness mean: {image_quality['brightness_mean']:.2f}",
            f"- Dynamic range: {image_quality['dynamic_range']:.2f}",
            f"- Flags: blurry={image_quality['is_blurry']}, too_dark={image_quality['is_too_dark']}, too_bright={image_quality['is_too_bright']}, low_contrast={image_quality['is_low_contrast']}",
            "",
            "SAÚDE DAS CÂMARAS",
            f"- Resumo: {camera_health}",
            "",
            "ARTEFACTOS",
            f"- Frame original: {files['original_frame']}",
            f"- Frame anotado: {files['annotated_frame']}",
            f"- Vídeos: {videos}",
            "",
        ]

        return "\n".join(lines)