from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel


class InfoPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Estado")

        self.lbl_config = QLabel("-")
        self.lbl_competition = QLabel("-")
        self.lbl_cameras = QLabel("-")
        self.lbl_health = QLabel("-")
        self.lbl_calibration = QLabel("-")
        self.lbl_attempt = QLabel("-")
        self.lbl_preview = QLabel("-")
        self.lbl_recording = QLabel("-")
        self.lbl_frame_selection = QLabel("-")
        self.lbl_point_selection = QLabel("-")
        self.lbl_measurement = QLabel("-")
        self.lbl_database = QLabel("-")
        self.lbl_athlete_summary = QLabel("-")

        for lbl in (
            self.lbl_config,
            self.lbl_competition,
            self.lbl_cameras,
            self.lbl_health,
            self.lbl_calibration,
            self.lbl_attempt,
            self.lbl_preview,
            self.lbl_recording,
            self.lbl_frame_selection,
            self.lbl_point_selection,
            self.lbl_measurement,
            self.lbl_database,
            self.lbl_athlete_summary,
        ):
            lbl.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Config", self.lbl_config)
        form.addRow("Competição", self.lbl_competition)
        form.addRow("Câmaras", self.lbl_cameras)
        form.addRow("Saúde", self.lbl_health)
        form.addRow("Calibração", self.lbl_calibration)
        form.addRow("Tentativa", self.lbl_attempt)
        form.addRow("Preview", self.lbl_preview)
        form.addRow("Gravação", self.lbl_recording)
        form.addRow("Frame", self.lbl_frame_selection)
        form.addRow("Ponto", self.lbl_point_selection)
        form.addRow("Medição", self.lbl_measurement)
        form.addRow("BD", self.lbl_database)
        form.addRow("Resumo atleta", self.lbl_athlete_summary)

        self.setLayout(form)