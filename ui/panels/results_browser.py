from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from database import CompetitionRecord


class ResultsBrowserPanel(QGroupBox):
    open_attempt_requested = Signal(int)
    athlete_summary_requested = Signal(int)
    archive_attempt_requested = Signal(int)
    unarchive_attempt_requested = Signal(int)
    delete_attempt_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__("Resultados")

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filtrar por atleta ou dorsal")

        self.competition_filter_combo = QComboBox()
        self.competition_filter_combo.addItem("Todas as competições", None)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Mais recentes", "recent_desc")
        self.sort_combo.addItem("Mais antigas", "recent_asc")
        self.sort_combo.addItem("Maior distância", "distance_desc")
        self.sort_combo.addItem("Menor distância", "distance_asc")
        self.sort_combo.addItem("Atleta A-Z", "athlete_asc")

        self.chk_include_archived = QCheckBox("Incluir arquivadas")

        self.btn_refresh = QPushButton("Atualizar")
        self.btn_open = QPushButton("Abrir tentativa")
        self.btn_summary = QPushButton("Resumo atleta")
        self.btn_archive = QPushButton("Arquivar")
        self.btn_unarchive = QPushButton("Desarquivar")
        self.btn_delete = QPushButton("Eliminar")

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Attempt DB",
            "Atleta",
            "Dorsal",
            "Competição",
            "Distância (cm)",
            "Frame",
            "Arquivada",
            "Criado em",
            "Dir",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)

        filters = QHBoxLayout()
        filters.addWidget(self.filter_edit, stretch=2)
        filters.addWidget(self.competition_filter_combo, stretch=2)
        filters.addWidget(self.sort_combo, stretch=1)
        filters.addWidget(self.chk_include_archived)
        filters.addWidget(self.btn_refresh)
        filters.addWidget(self.btn_open)
        filters.addWidget(self.btn_summary)
        filters.addWidget(self.btn_archive)
        filters.addWidget(self.btn_unarchive)
        filters.addWidget(self.btn_delete)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.table)

        self.btn_open.clicked.connect(self._emit_open_selected)
        self.btn_summary.clicked.connect(self._emit_summary_selected)
        self.btn_archive.clicked.connect(self._emit_archive_selected)
        self.btn_unarchive.clicked.connect(self._emit_unarchive_selected)
        self.btn_delete.clicked.connect(self._emit_delete_selected)
        self.table.cellDoubleClicked.connect(lambda *_: self._emit_open_selected())
        self.table.itemSelectionChanged.connect(self._update_action_buttons)

        self._update_action_buttons()

    def set_competitions(self, competitions: list[CompetitionRecord]) -> None:
        selected = self.selected_competition_filter_id()

        self.competition_filter_combo.blockSignals(True)
        self.competition_filter_combo.clear()
        self.competition_filter_combo.addItem("Todas as competições", None)

        selected_index = 0
        for idx, comp in enumerate(competitions, start=1):
            label = f"{comp.name} | {comp.location} | {comp.event_date}"
            self.competition_filter_combo.addItem(label, comp.id)
            if selected is not None and comp.id == selected:
                selected_index = idx

        self.competition_filter_combo.setCurrentIndex(selected_index)
        self.competition_filter_combo.blockSignals(False)

    def set_results(self, rows: list[dict]) -> None:
        self.table.setRowCount(0)

        for row_idx, row in enumerate(rows):
            self.table.insertRow(row_idx)

            values = [
                str(row.get("attempt_id", "")),
                str(row.get("athlete_name", "")),
                str(row.get("bib_number", "")),
                str(row.get("competition_name", "") or "-"),
                "" if row.get("distance_cm") is None else f"{float(row['distance_cm']):.2f}",
                "" if row.get("frame_index") is None else str(row.get("frame_index")),
                "sim" if bool(row.get("is_archived")) else "não",
                str(row.get("attempt_created_at", "")),
                str(row.get("attempt_dir", "")),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, row)
                self.table.setItem(row_idx, col, item)

        self._update_action_buttons()

    def filtered_query(self) -> str:
        return self.filter_edit.text().strip()

    def include_archived(self) -> bool:
        return self.chk_include_archived.isChecked()

    def selected_competition_filter_id(self) -> Optional[int]:
        idx = self.competition_filter_combo.currentIndex()
        if idx < 0:
            return None
        value = self.competition_filter_combo.currentData()
        return int(value) if value is not None else None

    def selected_sort_mode(self) -> str:
        return str(self.sort_combo.currentData())

    def selected_row_payload(self) -> Optional[dict]:
        row_idx = self.table.currentRow()
        if row_idx < 0:
            return None

        item = self.table.item(row_idx, 0)
        if item is None:
            return None

        payload = item.data(Qt.UserRole)
        return payload if isinstance(payload, dict) else None

    def _update_action_buttons(self) -> None:
        payload = self.selected_row_payload()
        has_selection = payload is not None
        is_archived = bool(payload.get("is_archived")) if payload else False

        self.btn_open.setEnabled(has_selection)
        self.btn_summary.setEnabled(has_selection and payload.get("athlete_id") is not None if payload else False)
        self.btn_archive.setEnabled(has_selection and not is_archived)
        self.btn_unarchive.setEnabled(has_selection and is_archived)
        self.btn_delete.setEnabled(has_selection)

    def _emit_open_selected(self) -> None:
        payload = self.selected_row_payload()
        if payload is None:
            return
        self.open_attempt_requested.emit(int(payload["attempt_id"]))

    def _emit_summary_selected(self) -> None:
        payload = self.selected_row_payload()
        if payload is None:
            return
        athlete_id = payload.get("athlete_id")
        if athlete_id is None:
            return
        self.athlete_summary_requested.emit(int(athlete_id))

    def _emit_archive_selected(self) -> None:
        payload = self.selected_row_payload()
        if payload is None:
            return
        self.archive_attempt_requested.emit(int(payload["attempt_id"]))

    def _emit_unarchive_selected(self) -> None:
        payload = self.selected_row_payload()
        if payload is None:
            return
        self.unarchive_attempt_requested.emit(int(payload["attempt_id"]))

    def _emit_delete_selected(self) -> None:
        payload = self.selected_row_payload()
        if payload is None:
            return
        self.delete_attempt_requested.emit(int(payload["attempt_id"]))