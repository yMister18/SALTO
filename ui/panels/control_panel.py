from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class ControlPanel(QGroupBox):
    competition_create_requested = Signal()
    competition_refresh_requested = Signal()
    athlete_pick_requested = Signal()

    def __init__(self) -> None:
        super().__init__("Controlo da Tentativa")

        self.competition_combo = QComboBox()
        self.btn_new_competition = QPushButton("Nova competição")
        self.btn_refresh_competitions = QPushButton("Atualizar competições")

        self.athlete_name_edit = QLineEdit()
        self.athlete_name_edit.setPlaceholderText("Nome do atleta")
        self.bib_number_edit = QLineEdit()
        self.bib_number_edit.setPlaceholderText("Dorsal")
        self.btn_pick_athlete = QPushButton("Escolher atleta")

        self.camera_combo = QComboBox()
        self.calibration_name_edit = QLineEdit()
        self.calibration_name_edit.setPlaceholderText("Nome da calibração ativa")

        self.btn_initialize = QPushButton("Inicializar câmaras")
        self.btn_preview = QPushButton("Iniciar preview")
        self.btn_stop_preview = QPushButton("Parar preview")
        self.btn_calibrate = QPushButton("Calibrar")
        self.btn_record = QPushButton("Gravar tentativa")
        self.btn_select_frame = QPushButton("Selecionar frame")
        self.btn_measure = QPushButton("Selecionar ponto")
        self.btn_save = QPushButton("Medir + Guardar")

        self.btn_preview.setEnabled(False)
        self.btn_stop_preview.setEnabled(False)
        self.btn_calibrate.setEnabled(False)
        self.btn_record.setEnabled(False)
        self.btn_select_frame.setEnabled(False)
        self.btn_measure.setEnabled(False)
        self.btn_save.setEnabled(False)

        competition_row = QHBoxLayout()
        competition_row.addWidget(self.competition_combo, stretch=1)
        competition_row.addWidget(self.btn_new_competition)
        competition_row.addWidget(self.btn_refresh_competitions)

        athlete_row = QHBoxLayout()
        athlete_row.addWidget(self.athlete_name_edit, stretch=2)
        athlete_row.addWidget(self.bib_number_edit, stretch=1)
        athlete_row.addWidget(self.btn_pick_athlete)

        form = QFormLayout()
        form.addRow("Competição", competition_row)
        form.addRow("Atleta / Dorsal", athlete_row)
        form.addRow("Câmara análise", self.camera_combo)
        form.addRow("Calibração", self.calibration_name_edit)

        buttons_layout = QVBoxLayout()
        buttons_layout.addWidget(self.btn_initialize)
        buttons_layout.addWidget(self.btn_preview)
        buttons_layout.addWidget(self.btn_stop_preview)
        buttons_layout.addWidget(self.btn_calibrate)
        buttons_layout.addWidget(self.btn_record)
        buttons_layout.addWidget(self.btn_select_frame)
        buttons_layout.addWidget(self.btn_measure)
        buttons_layout.addWidget(self.btn_save)
        buttons_layout.addStretch(1)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addSpacing(10)
        root.addLayout(buttons_layout)

        self.btn_new_competition.clicked.connect(self.competition_create_requested.emit)
        self.btn_refresh_competitions.clicked.connect(self.competition_refresh_requested.emit)
        self.btn_pick_athlete.clicked.connect(self.athlete_pick_requested.emit)

    def selected_competition_id(self) -> Optional[int]:
        idx = self.competition_combo.currentIndex()
        if idx < 0:
            return None
        data = self.competition_combo.currentData()
        return int(data) if data is not None else None