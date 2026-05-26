from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import cv2
import numpy as np

from camera_manager import FramePacket


@dataclass(frozen=True)
class FrameSelectionResult:
    camera_id: int
    frame_index: int
    timestamp: float
    frame: np.ndarray


class FrameSelectionCancelled(RuntimeError):
    pass


class FrameSelector:
    """
    Navegação manual sobre uma sequência de frames já capturados.

    Controlo:
    - LEFT / RIGHT: frame anterior / seguinte
    - A / D: -10 / +10 frames
    - Q / E: -50 / +50 frames
    - HOME: primeiro frame
    - END: último frame
    - ENTER: confirmar frame
    - ESC: cancelar
    """

    def __init__(
        self,
        window_name: str = "LAP2GO - Frame Selector",
        max_preview_width: int = 1600,
        max_preview_height: int = 900,
    ) -> None:
        self.window_name = window_name
        self.max_preview_width = max_preview_width
        self.max_preview_height = max_preview_height

    def select_frame(
        self,
        frames: Sequence[FramePacket],
        initial_index: int | None = None,
    ) -> FrameSelectionResult:
        if not frames:
            raise ValueError("A lista de frames está vazia.")

        index = initial_index if initial_index is not None else len(frames) // 2
        index = max(0, min(index, len(frames) - 1))

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)

        while True:
            camera_id, timestamp, frame = frames[index]
            preview = self._build_preview(
                frame=frame,
                index=index,
                total=len(frames),
                timestamp=timestamp,
                camera_id=camera_id,
            )
            cv2.imshow(self.window_name, preview)

            key = cv2.waitKeyEx(0)

            if key in (13, 10):
                cv2.destroyWindow(self.window_name)
                return FrameSelectionResult(
                    camera_id=camera_id,
                    frame_index=index,
                    timestamp=timestamp,
                    frame=frame.copy(),
                )
            if key == 27:
                cv2.destroyWindow(self.window_name)
                raise FrameSelectionCancelled("Seleção de frame cancelada pelo utilizador.")

            if key in (81, 2424832):
                index = max(0, index - 1)
            elif key in (83, 2555904):
                index = min(len(frames) - 1, index + 1)
            elif key in (ord("a"), ord("A")):
                index = max(0, index - 10)
            elif key in (ord("d"), ord("D")):
                index = min(len(frames) - 1, index + 10)
            elif key in (ord("q"), ord("Q")):
                index = max(0, index - 50)
            elif key in (ord("e"), ord("E")):
                index = min(len(frames) - 1, index + 50)
            elif key in (36, 2359296):
                index = 0
            elif key in (35, 2293760):
                index = len(frames) - 1

    def _build_preview(
        self,
        frame: np.ndarray,
        index: int,
        total: int,
        timestamp: float,
        camera_id: int,
    ) -> np.ndarray:
        preview = frame.copy()
        height, width = preview.shape[:2]

        scale = min(
            self.max_preview_width / width,
            self.max_preview_height / height,
            1.0,
        )
        if scale < 1.0:
            preview = cv2.resize(
                preview,
                (int(width * scale), int(height * scale)),
                interpolation=cv2.INTER_AREA,
            )

        overlay = preview.copy()
        cv2.rectangle(overlay, (10, 10), (preview.shape[1] - 10, 140), (0, 0, 0), -1)
        preview = cv2.addWeighted(overlay, 0.45, preview, 0.55, 0)

        lines = [
            f"CAM={camera_id} | frame={index + 1}/{total}",
            f"timestamp={timestamp:.3f}",
            "LEFT/RIGHT: -/+1 | A/D: -/+10 | Q/E: -/+50 | HOME/END: extremos",
            "ENTER: confirmar frame | ESC: cancelar",
        ]

        y = 40
        for i, line in enumerate(lines):
            scale_text = 0.9 if i < 2 else 0.7
            thickness = 2 if i < 2 else 1
            cv2.putText(
                preview,
                line,
                (24, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                scale_text,
                (255, 255, 255),
                thickness,
                cv2.LINE_AA,
            )
            y += 28

        return preview