from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        duration_seconds: float,
        pre_buffer_seconds: float,
        default_calibration_name: str,
        distance_precision_decimals: int,
        call_line_p1: tuple[float, float],
        call_line_p2: tuple[float, float],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuração Operacional")
        self.resize(560, 340)

        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.1, 1200.0)
        self.duration_spin.setDecimals(2)
        self.duration_spin.setValue(duration_seconds)

        self.pre_buffer_spin = QDoubleSpinBox()
        self.pre_buffer_spin.setRange(0.0, 1200.0)
        self.pre_buffer_spin.setDecimals(2)
        self.pre_buffer_spin.setValue(pre_buffer_seconds)

        self.calibration_name_edit = QLineEdit(default_calibration_name)

        self.distance_precision_spin = QSpinBox()
        self.distance_precision_spin.setRange(0, 6)
        self.distance_precision_spin.setValue(distance_precision_decimals)

        self.call_line_p1_edit = QLineEdit(f"{call_line_p1[0]},{call_line_p1[1]}")
        self.call_line_p2_edit = QLineEdit(f"{call_line_p2[0]},{call_line_p2[1]}")

        self.btn_apply = QPushButton("Aplicar")
        self.btn_cancel = QPushButton("Cancelar")

        self.btn_apply.clicked.connect(self._validate_and_accept)
        self.btn_cancel.clicked.connect(self.reject)

        form = QFormLayout()
        form.addRow("Duração gravação (s)", self.duration_spin)
        form.addRow("Pre-buffer (s)", self.pre_buffer_spin)
        form.addRow("Calibração default", self.calibration_name_edit)
        form.addRow("Precisão distância", self.distance_precision_spin)
        form.addRow("Linha chamada P1 (x,y)", self.call_line_p1_edit)
        form.addRow("Linha chamada P2 (x,y)", self.call_line_p2_edit)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.btn_apply)
        actions.addWidget(self.btn_cancel)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(actions)

    def _validate_and_accept(self) -> None:
        try:
            self.payload()
        except Exception as exc:
            QMessageBox.critical(self, "Configuração inválida", str(exc))
            return
        self.accept()

    def payload(self) -> dict:
        calibration_name = self.calibration_name_edit.text().strip()
        if not calibration_name:
            raise RuntimeError("O nome da calibração não pode estar vazio.")

        p1 = self._parse_point(self.call_line_p1_edit.text().strip(), "P1")
        p2 = self._parse_point(self.call_line_p2_edit.text().strip(), "P2")

        if p1 == p2:
            raise RuntimeError("A linha de chamada precisa de dois pontos diferentes.")

        return {
            "duration_seconds": float(self.duration_spin.value()),
            "pre_buffer_seconds": float(self.pre_buffer_spin.value()),
            "default_calibration_name": calibration_name,
            "distance_precision_decimals": int(self.distance_precision_spin.value()),
            "call_line_p1": p1,
            "call_line_p2": p2,
        }

    def _parse_point(self, text: str, label: str) -> tuple[float, float]:
        try:
            x_str, y_str = text.split(",")
            return (float(x_str.strip()), float(y_str.strip()))
        except Exception as exc:
            raise RuntimeError(f"{label} inválido. Use formato x,y") from exc