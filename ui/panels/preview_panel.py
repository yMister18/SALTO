import numpy as np
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
import numpy as np

# Assume que existe este helper
def cv2_frame_to_qpixmap(frame_bgr: np.ndarray):
    from PySide6.QtGui import QPixmap, QImage
    h, w, ch = frame_bgr.shape
    bytes_per_line = ch * w
    qimg = QImage(
        frame_bgr.data, w, h, bytes_per_line,
        QImage.Format.Format_BGR888
    )
    return QPixmap.fromImage(qimg)

class PreviewImageLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(True)
    def set_preview_pixmap(self, pixmap):
        self.setPixmap(pixmap)
    def clear_preview(self, text=""):
        self.clear()
        self.setText(text)

class CameraPreviewWidget(QGroupBox):
    def __init__(self, title: str = "Preview") -> None:
        super().__init__(title)
        self.preview_label = PreviewImageLabel()
        self.preview_label.setMinimumSize(960, 540)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #101010;
                color: #dddddd;
                border: 1px solid #444444;
                font-size: 18px;
            }
        """)
        self.preview_label.setText("Preview multi-câmara indisponível")

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview_label)

    def set_message(self, text: str) -> None:
        self.preview_label.clear_preview(text)

    def set_frame(self, frame_bgr: np.ndarray) -> None:
        if frame_bgr is None or frame_bgr.size == 0:
            self.set_message("Frame inválido")
            return
        pixmap = cv2_frame_to_qpixmap(frame_bgr)
        self.preview_label.setText("")
        self.preview_label.set_preview_pixmap(pixmap)