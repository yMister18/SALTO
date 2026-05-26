from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from merge_analyzer import ImpactAnalyzer
from ui.models import AppContext
from ui.widgets.point_selection_canvas import PointSelectionCanvas


class PointSelectionDialog(QDialog):
    def __init__(self, context: AppContext, frame_bgr: np.ndarray, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.context = context
        self.frame_bgr = frame_bgr.copy()
        self.clicked_point: Optional[tuple[int, int]] = None
        self.final_point: Optional[tuple[int, int]] = None

        self.setWindowTitle("Seleção de Ponto de Impacto")
        self.resize(1450, 980)

        self.canvas = PointSelectionCanvas()
        self.canvas.set_image(self.frame_bgr)
        self.canvas.point_clicked.connect(self._on_point_clicked)
        self.canvas.point_dragged.connect(self._on_point_dragged)

        self.info_label = QLabel(self._build_info_text())
        self.info_label.setWordWrap(True)

        self.btn_zoom_in = QPushButton("Zoom +")
        self.btn_zoom_out = QPushButton("Zoom -")
        self.btn_left = QPushButton("←")
        self.btn_right = QPushButton("→")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        self.btn_reapply_snap = QPushButton("Reaplicar snap")
        self.btn_use_clicked = QPushButton("Usar clique bruto")
        self.btn_confirm = QPushButton("Confirmar ponto")
        self.btn_cancel = QPushButton("Cancelar")

        self.btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        self.btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        self.btn_left.clicked.connect(lambda: self.canvas.pan(-80, 0))
        self.btn_right.clicked.connect(lambda: self.canvas.pan(80, 0))
        self.btn_up.clicked.connect(lambda: self.canvas.pan(0, -80))
        self.btn_down.clicked.connect(lambda: self.canvas.pan(0, 80))
        self.btn_reapply_snap.clicked.connect(self._reapply_snap)
        self.btn_use_clicked.clicked.connect(self._use_clicked_point)
        self.btn_confirm.clicked.connect(self._accept)
        self.btn_cancel.clicked.connect(self.reject)

        nav = QHBoxLayout()
        nav.addWidget(self.btn_zoom_in)
        nav.addWidget(self.btn_zoom_out)
        nav.addSpacing(20)
        nav.addWidget(self.btn_left)
        nav.addWidget(self.btn_right)
        nav.addWidget(self.btn_up)
        nav.addWidget(self.btn_down)
        nav.addSpacing(20)
        nav.addWidget(self.btn_reapply_snap)
        nav.addWidget(self.btn_use_clicked)
        nav.addStretch(1)
        nav.addWidget(self.btn_confirm)
        nav.addWidget(self.btn_cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self.info_label)
        layout.addLayout(nav)

    def _on_point_clicked(self, x: int, y: int) -> None:
        self.clicked_point = (x, y)
        self.final_point = self._apply_snap(self.clicked_point)
        self.canvas.set_points(self.clicked_point, self.final_point)
        if self.final_point is not None:
            self.canvas.center_on_point(self.final_point)
        self.info_label.setText(self._build_info_text())

    def _on_point_dragged(self, x: int, y: int) -> None:
        self.final_point = (x, y)
        self.canvas.set_points(self.clicked_point, self.final_point)
        self.info_label.setText(self._build_info_text())

    def _reapply_snap(self) -> None:
        if self.clicked_point is None:
            return
        self.final_point = self._apply_snap(self.clicked_point)
        self.canvas.set_points(self.clicked_point, self.final_point)
        if self.final_point is not None:
            self.canvas.center_on_point(self.final_point)
        self.info_label.setText(self._build_info_text())

    def _use_clicked_point(self) -> None:
        if self.clicked_point is None:
            return
        self.final_point = self.clicked_point
        self.canvas.set_points(self.clicked_point, self.final_point)
        self.info_label.setText(self._build_info_text())

    def _apply_snap(self, point: tuple[int, int]) -> tuple[int, int]:
        analyzer = ImpactAnalyzer(self.context.calibration_manager)
        return analyzer.smart_snap(self.frame_bgr, point)

    def _accept(self) -> None:
        if self.clicked_point is None or self.final_point is None:
            QMessageBox.warning(self, "Seleção", "Selecione primeiro um ponto.")
            return
        self.accept()

    def _build_info_text(self) -> str:
        return (
            f"Clicked point: {self.clicked_point}\n"
            f"Final point: {self.final_point}\n"
            f"O clique bruto é do operador; o ponto final pode ser snap ou correção manual."
        )