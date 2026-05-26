from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from ui.models import AppContext, AttemptRuntimeState


class AttemptController:
    def __init__(self, context: AppContext, set_state_cb=None, set_ui_cb=None):
        """
        set_state_cb: função chamada após update de AttemptRuntimeState
        set_ui_cb: função chamada para refresh na UI (opcional)
        """
        self.context = context
        self.state = AttemptRuntimeState()
        self.set_state_cb = set_state_cb
        self.set_ui_cb = set_ui_cb

    def reset(self, preserve_identity: bool = False) -> None:
        """
        Limpa estado da tentativa, opcionalmente mantendo info de atleta/competição.
        """
        if preserve_identity:
            athlete_name = self.state.athlete_name
            bib_number = self.state.bib_number
            athlete_db_id = self.state.athlete_db_id
            competition_db_id = self.state.competition_db_id
        else:
            athlete_name = ""
            bib_number = ""
            athlete_db_id = None
            competition_db_id = None

        self.state = AttemptRuntimeState(
            athlete_name=athlete_name,
            bib_number=bib_number,
            athlete_db_id=athlete_db_id,
            competition_db_id=competition_db_id,
        )
        self._publish_state()
        self._publish_ui()

    def apply_identity(
        self,
        athlete_name: str,
        bib_number: str,
        athlete_db_id: Optional[int] = None,
        competition_db_id: Optional[int] = None,
        attempt_db_id: Optional[int] = None,
        attempt_dir: Optional[Path] = None,
        analysis_camera_id: Optional[int] = None,
        recording_session=None,
    ) -> None:
        s = self.state
        s.athlete_name = athlete_name
        s.bib_number = bib_number
        s.athlete_db_id = athlete_db_id
        s.competition_db_id = competition_db_id
        s.attempt_db_id = attempt_db_id
        s.attempt_dir = attempt_dir
        s.analysis_camera_id = analysis_camera_id
        s.recording_session = recording_session
        self._publish_state()
        self._publish_ui()

    def apply_selected_frame(
        self, 
        frame_bgr: Optional[np.ndarray], 
        frame_index: Optional[int], 
        frame_timestamp: Optional[float]
    ) -> None:
        s = self.state
        s.selected_frame_bgr = frame_bgr.copy() if frame_bgr is not None else None
        s.selected_frame_index = frame_index
        s.selected_frame_timestamp = frame_timestamp
        s.clicked_point_px = None
        s.final_point_px = None
        s.distance_cm = None
        s.measurement_payload = None
        self._publish_state()
        self._publish_ui()

    def apply_selected_points(
        self, 
        clicked_point: Optional[tuple[int, int]], 
        final_point: Optional[tuple[int, int]]
    ) -> None:
        s = self.state
        s.clicked_point_px = clicked_point
        s.final_point_px = final_point
        s.distance_cm = None
        s.measurement_payload = None
        self._publish_state()
        self._publish_ui()

    def apply_measurement_result(
        self, 
        distance_cm: Optional[float], 
        measurement_payload: Optional[dict] = None
    ) -> None:
        s = self.state
        s.distance_cm = distance_cm
        s.measurement_payload = measurement_payload
        self._publish_state()
        self._publish_ui()

    def update_from_db_detail(self, detail: dict) -> None:
        # Reconstrói o estado da tentativa a partir de um detail (resultado da DB)
        from pathlib import Path
        import json
        import cv2

        attempt_dir = Path(str(detail["attempt_dir"]))
        athlete_name = str(detail.get("athlete_name", "") or "")
        bib_number = str(detail.get("bib_number", "") or "")
        athlete_id = detail.get("athlete_id")
        competition_id = detail.get("competition_id")
        analysis_camera_id = detail.get("analysis_camera_id")
        frame_index = detail.get("frame_index")
        frame_timestamp = detail.get("frame_timestamp")
        distance_cm = detail.get("distance_cm")
        measurement_json_path = detail.get("measurement_json_path")

        measurement_payload = None
        selected_frame_bgr = None
        clicked_point_px = None
        final_point_px = None

        if measurement_json_path:
            measurement_json_file = Path(measurement_json_path)
            if measurement_json_file.exists():
                try:
                    measurement_payload = json.loads(measurement_json_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

        if measurement_payload is not None:
            clicked = measurement_payload.get("clicked_point_px")
            final = measurement_payload.get("final_point_px")
            if isinstance(clicked, (list, tuple)) and len(clicked) == 2:
                clicked_point_px = (int(clicked[0]), int(clicked[1]))
            if isinstance(final, (list, tuple)) and len(final) == 2:
                final_point_px = (int(final[0]), int(final[1]))

            original_frame_path = (
                measurement_payload.get("files", {}).get("original_frame")
                if isinstance(measurement_payload.get("files"), dict)
                else None
            )
            if original_frame_path and Path(original_frame_path).exists():
                frame = cv2.imread(str(original_frame_path))
                if frame is not None:
                    selected_frame_bgr = frame

        self.state = AttemptRuntimeState(
            athlete_name=athlete_name,
            bib_number=bib_number,
            athlete_db_id=int(athlete_id) if athlete_id is not None else None,
            competition_db_id=int(competition_id) if competition_id is not None else None,
            attempt_db_id=int(detail["attempt_id"]),
            attempt_dir=attempt_dir,
            analysis_camera_id=int(analysis_camera_id) if analysis_camera_id is not None else None,
            recording_session=None,
            selected_frame_index=int(frame_index) if frame_index is not None else None,
            selected_frame_timestamp=float(frame_timestamp) if frame_timestamp is not None else None,
            selected_frame_bgr=selected_frame_bgr,
            clicked_point_px=clicked_point_px,
            final_point_px=final_point_px,
            distance_cm=float(distance_cm) if distance_cm is not None else None,
            measurement_payload=measurement_payload,
        )
        self._publish_state()
        self._publish_ui()

    def _publish_state(self):
        if self.set_state_cb:
            self.set_state_cb(self.state)

    def _publish_ui(self):
        if self.set_ui_cb:
            self.set_ui_cb(self.state)