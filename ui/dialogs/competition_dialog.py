from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class CompetitionDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nova Competição")
        self.resize(500, 220)

        self.name_edit = QLineEdit()
        self.location_edit = QLineEdit()
        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText("YYYY-MM-DD")

        self.btn_create = QPushButton("Criar")
        self.btn_cancel = QPushButton("Cancelar")

        self.btn_create.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        form = QFormLayout()
        form.addRow("Nome", self.name_edit)
        form.addRow("Local", self.location_edit)
        form.addRow("Data", self.date_edit)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.btn_create)
        actions.addWidget(self.btn_cancel)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(actions)

    def payload(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "location": self.location_edit.text().strip(),
            "event_date": self.date_edit.text().strip(),
        }