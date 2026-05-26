from __future__ import annotations

from typing import Optional

import cv2
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from camera_manager import FramePacket
from ui.panels.preview_panel import PreviewImageLabel, cv2_frame_to_qpixmap


class FrameSelectionDialog(QDialog):
    def __init__(self, frames: list[FramePacket], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.frames = frames
        self.selected_index: Optional[int] = None

        self.setWindowTitle("Seleção de Frame")
        self.resize(1400, 900)

        self.preview = PreviewImageLabel()
        self.preview.setMinimumSize(1100, 620)
        self.preview.setStyleSheet("""
            QLabel {
                background-color: #101010;
                border: 1px solid #444444;
                color: #dddddd;
            }
        """)

        self.info_label = QLabel("-")
        self.info_label.setWordWrap(True)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(max(0, len(frames) - 1))
        self.slider.setValue(0)

        self.btn_prev = QPushButton("Anterior")
        self.btn_next = QPushButton("Seguinte")
        self.btn_prev10 = QPushButton("-10")
        self.btn_next10 = QPushButton("+10")

        self.btn_confirm = QPushButton("Confirmar frame")
        self.btn_cancel = QPushButton("Cancelar")

        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_next.clicked.connect(self._go_next)
        self.btn_prev10.clicked.connect(lambda: self._jump(-10))
        self.btn_next10.clicked.connect(lambda: self._jump(+10))
        self.slider.valueChanged.connect(self._render_current_frame)
        self.btn_confirm.clicked.connect(self._accept)
        self.btn_cancel.clicked.connect(self.reject)

        nav = QHBoxLayout()
        nav.addWidget(self.btn_prev10)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.slider, stretch=1)
        nav.addWidget(self.btn_next)
        nav.addWidget(self.btn_next10)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.btn_confirm)
        actions.addWidget(self.btn_cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview, stretch=1)
        layout.addWidget(self.info_label)
        layout.addLayout(nav)
        layout.addLayout(actions)

        if self.frames:
            self._render_current_frame(0)

    def selected_packet(self) -> Optional[FramePacket]:
        if self.selected_index is None or not self.frames:
            return None
        return self.frames[self.selected_index]

    def _go_prev(self) -> None:
        self.slider.setValue(max(0, self.slider.value() - 1))

    def _go_next(self) -> None:
        self.slider.setValue(min(self.slider.maximum(), self.slider.value() + 1))

    def _jump(self, offset: int) -> None:
        self.slider.setValue(max(0, min(self.slider.maximum(), self.slider.value() + offset)))

    def _render_current_frame(self, index: int) -> None:
        if not self.frames:
            self.preview.clear_preview("Sem frames")
            self.info_label.setText("Sem frames disponíveis.")
            return

        camera_id, ts, frame = self.frames[index]
        preview_frame = frame.copy()

        cv2.rectangle(preview_frame, (10, 10), (780, 90), (0, 0, 0), -1)
        cv2.putText(
            preview_frame,
            f"CAM {camera_id} | frame {index + 1}/{len(self.frames)} | ts={ts:.3f}",
            (24, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.95,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        self.preview.set_preview_pixmap(cv2_frame_to_qpixmap(preview_frame))
        self.info_label.setText(f"Câmara: {camera_id} | Índice: {index} | Timestamp: {ts:.3f}")

    def _accept(self) -> None:
        if not self.frames:
            QMessageBox.warning(self, "Seleção", "Sem frames disponíveis.")
            return
        self.selected_index = int(self.slider.value())
        self.accept()