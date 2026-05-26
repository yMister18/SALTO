from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from database import AthleteRecord


class AthletePickerDialog(QDialog):
    athlete_selected = Signal(int, str, str)

    def __init__(self, athletes: list[AthleteRecord], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Selecionar Atleta")
        self.resize(600, 500)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filtrar por atleta ou dorsal")
        self.list_widget = QListWidget()

        self.btn_select = QPushButton("Selecionar")
        self.btn_cancel = QPushButton("Cancelar")

        self.all_athletes = athletes
        self.filtered_athletes = athletes[:]

        self.search_edit.textChanged.connect(self._filter)
        self.btn_select.clicked.connect(self._select_current)
        self.btn_cancel.clicked.connect(self.reject)
        self.list_widget.itemDoubleClicked.connect(lambda *_: self._select_current())

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.btn_select)
        actions.addWidget(self.btn_cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.list_widget, stretch=1)
        layout.addLayout(actions)

        self._rebuild_list()

    def _filter(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            self.filtered_athletes = self.all_athletes[:]
        else:
            self.filtered_athletes = [
                athlete
                for athlete in self.all_athletes
                if query in athlete.athlete_name.lower() or query in athlete.bib_number.lower()
            ]
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        self.list_widget.clear()
        for athlete in self.filtered_athletes:
            item = QListWidgetItem(f"{athlete.athlete_name} | dorsal={athlete.bib_number} | id={athlete.id}")
            item.setData(Qt.UserRole, athlete)
            self.list_widget.addItem(item)

    def _select_current(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        athlete = item.data(Qt.UserRole)
        if not isinstance(athlete, AthleteRecord):
            return
        self.athlete_selected.emit(athlete.id, athlete.athlete_name, athlete.bib_number)
        self.accept()