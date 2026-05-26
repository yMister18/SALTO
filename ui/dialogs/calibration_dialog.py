from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_config import CalibrationPreset
from ui.models import AppContext
from ui.widgets.calibration_canvas import CalibrationCanvas


class CalibrationDialog(QDialog):
    def __init__(self, context: AppContext, frame_bgr: np.ndarray, calibration_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.context = context
        self.frame_bgr = frame_bgr.copy()
        self.calibration_name = calibration_name
        self.required_points = context.config.calibration.min_points
        self.points: list[tuple[int, int]] = []

        self.setWindowTitle("Calibração Visual")
        self.resize(1280, 860)

        self.canvas = CalibrationCanvas()
        self.canvas.set_image(self.frame_bgr)
        self.canvas.point_added.connect(self._on_point_added)

        self.info_label = QLabel(self._build_info_text())
        self.info_label.setWordWrap(True)

        self.btn_remove_last = QPushButton("Remover último")
        self.btn_clear = QPushButton("Limpar")
        self.btn_use_preset = QPushButton("Usar preset e guardar")
        self.btn_manual_world = QPushButton("Inserir pontos reais e guardar")

        self.btn_remove_last.clicked.connect(self._remove_last)
        self.btn_clear.clicked.connect(self._clear_points)
        self.btn_use_preset.clicked.connect(self._save_with_preset)
        self.btn_manual_world.clicked.connect(self._save_with_manual_world_points)

        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_remove_last)
        buttons.addWidget(self.btn_clear)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_use_preset)
        buttons.addWidget(self.btn_manual_world)

        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self.info_label)
        layout.addLayout(buttons)

    def _on_point_added(self, x: int, y: int) -> None:
        if len(self.points) >= self.required_points:
            return
        self.points.append((x, y))
        self.canvas.set_points(self.points)
        self.info_label.setText(self._build_info_text())

    def _remove_last(self) -> None:
        if self.points:
            self.points.pop()
            self.canvas.set_points(self.points)
            self.info_label.setText(self._build_info_text())

    def _clear_points(self) -> None:
        self.points.clear()
        self.canvas.set_points(self.points)
        self.info_label.setText(self._build_info_text())

    def _save_with_preset(self) -> None:
        if len(self.points) != self.required_points:
            QMessageBox.warning(self, "Calibração", f"São necessários {self.required_points} pontos.")
            return
        preset = self._resolve_default_preset()
        self._save_calibration(preset.world_points_cm)

    def _save_with_manual_world_points(self) -> None:
        if len(self.points) != self.required_points:
            QMessageBox.warning(self, "Calibração", f"São necessários {self.required_points} pontos.")
            return

        world_points = []
        for idx in range(self.required_points):
            text, ok = QInputDialog.getText(self, "Ponto real", f"Ponto real #{idx + 1} no formato x,y (cm):")
            if not ok:
                return
            try:
                x_str, y_str = text.strip().split(",")
                world_points.append((float(x_str), float(y_str)))
            except Exception:
                QMessageBox.warning(self, "Erro", "Formato inválido. Use x,y")
                return

        self._save_calibration(world_points)

    def _save_calibration(self, world_points: list[tuple[float, float]]) -> None:
        try:
            data = self.context.calibration_manager.calibrate(
                image_points=self.points,
                world_points_cm=world_points,
                sandbox_name=self.calibration_name,
            )
            path = self.context.file_manager.calibration_path(self.calibration_name)
            self.context.calibration_manager.save(data, path)

            QMessageBox.information(
                self,
                "Calibração",
                f"Calibração guardada com sucesso.\n\n"
                f"Ficheiro: {path}\n"
                f"Erro médio: {data.quality.mean_reprojection_error_px:.3f} px\n"
                f"Erro máximo: {data.quality.max_reprojection_error_px:.3f} px",
            )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Erro na calibração", str(exc))

    def _resolve_default_preset(self) -> CalibrationPreset:
        preset_name = self.context.config.calibration.default_preset_name
        for preset in self.context.config.calibration.presets:
            if preset.name == preset_name:
                return preset
        raise RuntimeError(f"Preset não encontrado: {preset_name}")

    def _build_info_text(self) -> str:
        return (
            f"Calibração: {self.calibration_name}\n"
            f"Pontos selecionados: {len(self.points)}/{self.required_points}\n"
            f"Preset default: {self.context.config.calibration.default_preset_name}"
        )