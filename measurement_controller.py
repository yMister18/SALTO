from __future__ import annotations

from typing import Optional, Callable

import cv2
import numpy as np

from merge_analyzer import ImpactAnalyzer
from geometry import Line2D
from image_quality import ImageQualityAnalyzer
from reporting import ReportingManager
from file_manager import MeasurementRecord

class MeasurementController:
    """
    Controller para o fluxo frame → ponto → medição → persistência.
    Tudo que não é UI fica aqui.
    """
    def __init__(
        self,
        context,
        runtime_settings,
        attempt_state_getter: Callable[[], object],
        file_manager,
        database_manager,
        measurement_done_cb: Optional[Callable[[float, dict], None]] = None,
        preview_update_cb: Optional[Callable[[np.ndarray], None]] = None,
        error_cb: Optional[Callable[[str], None]] = None,
    ):
        self.context = context
        self.runtime_settings = runtime_settings
        self.get_attempt_state = attempt_state_getter
        self.file_manager = file_manager
        self.database_manager = database_manager
        self.measurement_done_cb = measurement_done_cb
        self.preview_update_cb = preview_update_cb
        self.error_cb = error_cb

    def compute_and_persist_measurement(self):
        """
        Executa o fluxo:
        1. Valida estado
        2. Calcula medição
        3. Persiste measurement.json, imagem anotada, CSV, report
        4. Atualiza BD
        5. Chama callbacks de finalização/UI
        """
        try:
            state = self.get_attempt_state()
            if state.selected_frame_bgr is None or state.final_point_px is None:
                raise RuntimeError("Frame ou ponto ainda não selecionados.")

            frame = state.selected_frame_bgr.copy()
            analyzer = ImpactAnalyzer(self.context.calibration_manager)
            quality_analyzer = ImageQualityAnalyzer()
            reporting = ReportingManager()

            call_line = Line2D(
                self.runtime_settings.default_call_line_world_cm[0],
                self.runtime_settings.default_call_line_world_cm[1],
            )

            measurement = analyzer.compute_measurement(
                frame=frame,
                clicked_point_px=state.final_point_px,
                call_line_world=call_line,
                auto_snap=False,
            )

            quality = quality_analyzer.analyze(frame)
            annotated = analyzer.draw_measurement_overlay(frame, measurement)
            annotated = quality_analyzer.draw_overlay(annotated, quality)

            attempt_dir = state.attempt_dir
            if attempt_dir is None:
                raise RuntimeError("attempt_dir em branco!")

            original_frame_path = self.file_manager.save_image(attempt_dir / "frame_original.png", frame)
            annotated_frame_path = self.file_manager.save_image(attempt_dir / "frame_annotated.png", annotated)

            measurement_payload = {
                "attempt_db_id": state.attempt_db_id,
                "athlete_name": state.athlete_name,
                "bib_number": state.bib_number,
                "analysis_camera_id": state.analysis_camera_id,
                "frame_index": state.selected_frame_index,
                "frame_timestamp": state.selected_frame_timestamp,
                "clicked_point_px": state.clicked_point_px,
                "final_point_px": state.final_point_px,
                "world_point_cm": measurement.world_point_cm,
                "distance_cm": round(measurement.distance_cm, self.runtime_settings.distance_precision_decimals),
                "projection_on_call_line_cm": measurement.projection_on_call_line_cm,
                "snap_debug": {
                    "clicked": state.clicked_point_px,
                    "final": state.final_point_px,
                },
                "image_quality": {
                    "sharpness": quality.sharpness if hasattr(quality, "sharpness") else None,
                },
                "files": {
                    "original_frame": str(original_frame_path),
                    "annotated_frame": str(annotated_frame_path),
                },
            }

            measurement_json_path = self.file_manager.save_json(
                attempt_dir / "measurement.json",
                measurement_payload,
            )

            db_measurement = self.database_manager.upsert_measurement(
                attempt_id=state.attempt_db_id,
                distance_cm=round(measurement.distance_cm, self.runtime_settings.distance_precision_decimals),
                world_point_cm=measurement.world_point_cm,
                projection_cm=measurement.projection_on_call_line_cm,
                clicked_point_px=state.clicked_point_px,
                final_point_px=state.final_point_px,
                measurement_json_path=str(measurement_json_path),
                annotated_frame_path=str(annotated_frame_path),
            )

            csv_record = MeasurementRecord(
                attempt_id=attempt_dir.name,
                athlete_name=state.athlete_name,
                bib_number=state.bib_number,
                camera_id=state.analysis_camera_id or 0,
                frame_index=state.selected_frame_index or 0,
                timestamp_iso=self.file_manager.utc_now_iso(),
                clicked_point_px=state.clicked_point_px,
                snapped_point_px=state.final_point_px,
                world_point_cm=measurement.world_point_cm,
                distance_cm=round(measurement.distance_cm, self.runtime_settings.distance_precision_decimals),
                calibration_file="",  # preencher se conhecido
                original_frame_file=str(original_frame_path),
                annotated_frame_file=str(annotated_frame_path),
            )
            csv_path = self.file_manager.append_csv(
                self.file_manager.measurement_csv_path(),
                [csv_record],
            )

            reporting.save_manifest(
                attempt_dir / "manifest.json",
                {
                    "attempt_db_id": state.attempt_db_id,
                    "measurement_json": str(measurement_json_path),
                    "annotated_frame": str(annotated_frame_path),
                    "csv": str(csv_path),
                },
            )

            report_text = reporting.build_attempt_report_text(measurement_payload)
            reporting.save_attempt_report(attempt_dir / "attempt_report.txt", report_text)

            # call UI hooks
            if self.measurement_done_cb:
                self.measurement_done_cb(float(measurement.distance_cm), measurement_payload)
            if self.preview_update_cb:
                self.preview_update_cb(annotated)
            return measurement.distance_cm

        except Exception as exc:
            if self.error_cb:
                self.error_cb(str(exc))
            else:
                raise
