from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

from camera_manager import CameraManager, FramePacket


@dataclass(frozen=True)
class RecordingConfig:
    output_dir: str | Path
    session_fps: int = 30
    sync_tolerance_ms: float = 25.0
    min_required_cameras: int = 1
    poll_interval_seconds: float = 1 / 120.0
    video_codec: str = "mp4v"
    file_extension: str = ".mp4"
    write_timestamp_overlay: bool = False


@dataclass(frozen=True)
class RecordingStats:
    is_recording: bool
    started_at: float | None
    stopped_at: float | None
    elapsed_seconds: float
    cameras_with_frames: int
    total_frames_recorded: int
    frames_per_camera: Dict[int, int]


class RecordingSession:
    def __init__(self, config: RecordingConfig):
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._is_recording = False
        self._started_at: float | None = None
        self._stopped_at: float | None = None

        self._frames_by_camera: Dict[int, List[FramePacket]] = {}
        self._last_written_timestamp_by_camera: Dict[int, float] = {}

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start(self, preload_buffers: Optional[Dict[int, List[FramePacket]]] = None) -> None:
        self._is_recording = True
        self._started_at = time.time()
        self._stopped_at = None
        self._frames_by_camera.clear()
        self._last_written_timestamp_by_camera.clear()

        if preload_buffers:
            for camera_id, packets in preload_buffers.items():
                self._frames_by_camera[camera_id] = [
                    (cam_id, ts, frame.copy())
                    for cam_id, ts, frame in packets
                ]
                if packets:
                    self._last_written_timestamp_by_camera[camera_id] = max(ts for _, ts, _ in packets)

    def stop(self) -> None:
        self._is_recording = False
        self._stopped_at = time.time()

    def ingest_synchronized_packets(self, packets: Dict[int, FramePacket]) -> None:
        if not self._is_recording:
            return

        for camera_id, packet in packets.items():
            _, ts, frame = packet
            last_ts = self._last_written_timestamp_by_camera.get(camera_id)
            if last_ts is not None and ts <= last_ts:
                continue

            self._frames_by_camera.setdefault(camera_id, []).append(
                (camera_id, ts, frame.copy())
            )
            self._last_written_timestamp_by_camera[camera_id] = ts

    def record_for_duration(
        self,
        camera_manager: CameraManager,
        duration_seconds: float,
        include_pre_buffer_seconds: float = 0.0,
    ) -> None:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds deve ser > 0.")

        preload = None
        if include_pre_buffer_seconds > 0:
            end_ts = time.time()
            start_ts = end_ts - include_pre_buffer_seconds
            preload = camera_manager.get_time_window_packets(start_ts, end_ts)

        self.start(preload_buffers=preload)

        deadline = time.time() + duration_seconds
        while time.time() < deadline:
            packets = camera_manager.get_synchronized_packets(
                tolerance_ms=self.config.sync_tolerance_ms
            )
            if len(packets) >= self.config.min_required_cameras:
                self.ingest_synchronized_packets(packets)
            time.sleep(self.config.poll_interval_seconds)

        self.stop()

    def export_videos(self) -> Dict[int, Path]:
        outputs: Dict[int, Path] = {}

        for camera_id, packets in sorted(self._frames_by_camera.items()):
            if not packets:
                continue

            first_frame = packets[0][2]
            height, width = first_frame.shape[:2]

            output_path = self.output_dir / f"camera_{camera_id}{self.config.file_extension}"
            writer = cv2.VideoWriter(
                str(output_path),
                cv2.VideoWriter_fourcc(*self.config.video_codec),
                self.config.session_fps,
                (width, height),
            )

            if not writer.isOpened():
                raise RuntimeError(f"Não foi possível criar vídeo: {output_path}")

            for _, ts, frame in packets:
                frame_to_write = frame.copy()
                if self.config.write_timestamp_overlay:
                    self._draw_timestamp_overlay(frame_to_write, ts, camera_id)
                writer.write(frame_to_write)

            writer.release()
            outputs[camera_id] = output_path

        return outputs

    def get_frames(self, camera_id: int) -> List[FramePacket]:
        return [
            (cam_id, ts, frame.copy())
            for cam_id, ts, frame in self._frames_by_camera.get(camera_id, [])
        ]

    def get_all_frames(self) -> Dict[int, List[FramePacket]]:
        return {
            camera_id: self.get_frames(camera_id)
            for camera_id in sorted(self._frames_by_camera.keys())
        }

    def save_frame_images(
        self,
        camera_id: int,
        indices: List[int],
        output_subdir: str = "frames",
    ) -> List[Path]:
        packets = self._frames_by_camera.get(camera_id, [])
        if not packets:
            return []

        target_dir = self.output_dir / output_subdir / f"camera_{camera_id}"
        target_dir.mkdir(parents=True, exist_ok=True)

        saved_paths: List[Path] = []
        for index in indices:
            if index < 0 or index >= len(packets):
                continue
            _, ts, frame = packets[index]
            path = target_dir / f"frame_{index:06d}_{ts:.3f}.png"
            ok = cv2.imwrite(str(path), frame)
            if not ok:
                raise RuntimeError(f"Falha ao gravar frame: {path}")
            saved_paths.append(path)

        return saved_paths

    def stats(self) -> RecordingStats:
        total_frames = sum(len(v) for v in self._frames_by_camera.values())
        frames_per_camera = {
            camera_id: len(packets)
            for camera_id, packets in sorted(self._frames_by_camera.items())
        }

        if self._started_at is None:
            elapsed = 0.0
        else:
            end_ref = self._stopped_at if self._stopped_at is not None else time.time()
            elapsed = max(0.0, end_ref - self._started_at)

        return RecordingStats(
            is_recording=self._is_recording,
            started_at=self._started_at,
            stopped_at=self._stopped_at,
            elapsed_seconds=elapsed,
            cameras_with_frames=len([1 for packets in self._frames_by_camera.values() if packets]),
            total_frames_recorded=total_frames,
            frames_per_camera=frames_per_camera,
        )

    def _draw_timestamp_overlay(self, frame: np.ndarray, ts: float, camera_id: int) -> None:
        text = f"cam={camera_id} ts={ts:.3f}"
        cv2.rectangle(frame, (20, 20), (520, 80), (0, 0, 0), -1)
        cv2.putText(
            frame,
            text,
            (35, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )