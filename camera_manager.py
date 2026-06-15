from __future__ import annotations

import time
import threading
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Literal, Optional, Tuple

import cv2
import numpy as np


FramePacket = Tuple[int, float, np.ndarray]


@dataclass(frozen=True)
class CameraSourceConfig:
    camera_id: int
    name: str
    source_type: Literal["usb", "rtsp", "video_file"]
    source: str | int
    enabled: bool = True
    width: int = 3840
    height: int = 2160
    fps: int = 30
    buffer_seconds: int = 8
    fourcc: str = "MJPG"
    warmup_seconds: float = 1.0
    open_timeout_seconds: float = 5.0
    read_retry_sleep_seconds: float = 0.01
    drop_frames_if_behind: bool = True

    reconnect_enabled: bool = True
    reconnect_initial_delay_seconds: float = 0.5
    reconnect_max_delay_seconds: float = 5.0
    max_consecutive_read_failures: int = 25
    stale_timeout_seconds: float = 2.0
    frozen_frame_detection_enabled: bool = True
    frozen_frame_diff_threshold: float = 0.5
    max_identical_frames: int = 20
    healthcheck_down_after_seconds: float = 3.0


@dataclass(frozen=True)
class CameraRuntimeStats:
    camera_id: int
    name: str
    is_open: bool
    is_running: bool
    total_frames_read: int
    dropped_frames: int
    buffer_size: int
    last_timestamp: float | None
    frame_shape: tuple[int, int, int] | None
    consecutive_read_failures: int
    reconnect_count: int
    identical_frame_streak: int
    stream_state: str
    health_status: str


class CameraOpenError(RuntimeError):
    pass


class CameraReadError(RuntimeError):
    pass

class CameraStream:
    def __init__(self, config: CameraSourceConfig):
        self.config = config
        self.cap: Optional[cv2.VideoCapture] = None

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        self._last_packet: Optional[FramePacket] = None
        self._buffer: Deque[FramePacket] = deque(maxlen=max(1, config.buffer_seconds * config.fps * 2))

        self._total_frames_read = 0
        self._dropped_frames = 0
        self._consecutive_read_failures = 0
        self._reconnect_count = 0
        self._identical_frame_streak = 0

        self._last_frame_signature: Optional[float] = None
        self._stream_state: str = "idle"
        self._last_successful_frame_ts: float | None = None
        self._buffer: Deque[FramePacket] = deque(maxlen=max(1, config.buffer_seconds * config.fps))

    @property
    def is_running(self) -> bool:
        return self._running

    def open(self) -> None:
        self._release_capture()

        self._stream_state = "opening"
        self.cap = cv2.VideoCapture(self.config.source)
        started = time.time()

        while True:
            if self.cap is not None and self.cap.isOpened():
                break
            if time.time() - started > self.config.open_timeout_seconds:
                self._stream_state = "open_failed"
                raise CameraOpenError(
                    f"Timeout ao abrir câmara {self.config.camera_id} ({self.config.name})"
                )
            time.sleep(0.05)

        self._apply_capture_settings()
        self._stream_state = "warming"
        if self.config.warmup_seconds > 0:
            time.sleep(self.config.warmup_seconds)
        self._stream_state = "running"

    def _apply_capture_settings(self) -> None:
        if self.cap is None:
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.config.fps)

        if self.config.source_type != "rtsp":
            fourcc = cv2.VideoWriter_fourcc(*self.config.fourcc)
            self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)

        if self.config.drop_frames_if_behind:
            try:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

    def start(self) -> None:
        if not self.config.enabled:
            return
        if self._running:
            return

        self.open()
        self._running = True
        self._thread = threading.Thread(
            target=self._reader_loop,
            name=f"CameraStream-{self.config.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._release_capture()
        self._stream_state = "stopped"

    def _reader_loop(self) -> None:
        reconnect_delay = self.config.reconnect_initial_delay_seconds

        while self._running:
            if self.cap is None or not self.cap.isOpened():
                if not self.config.reconnect_enabled:
                    self._stream_state = "down"
                    time.sleep(self.config.read_retry_sleep_seconds)
                    continue

                self._stream_state = "reconnecting"
                try:
                    self.open()
                    reconnect_delay = self.config.reconnect_initial_delay_seconds
                    with self._lock:
                        self._reconnect_count += 1
                        self._consecutive_read_failures = 0
                except Exception:
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(
                        self.config.reconnect_max_delay_seconds,
                        reconnect_delay * 2,
                    )
                    continue

            ok, frame = self.cap.read() if self.cap is not None else (False, None)
            timestamp = time.time()

            if not ok or frame is None:
                with self._lock:
                    self._consecutive_read_failures += 1

                if self._consecutive_read_failures >= self.config.max_consecutive_read_failures:
                    self._stream_state = "read_failed"
                    self._force_reconnect()
                else:
                    self._stream_state = "degraded"

                time.sleep(self.config.read_retry_sleep_seconds)
                continue

            with self._lock:
                self._consecutive_read_failures = 0

            self._process_successful_frame(timestamp, frame)

    def _process_successful_frame(self, timestamp: float, frame: np.ndarray) -> None:
        signature = self._frame_signature(frame)

        with self._lock:
            if self.config.frozen_frame_detection_enabled:
                if self._last_frame_signature is not None:
                    diff = abs(signature - self._last_frame_signature)
                    if diff <= self.config.frozen_frame_diff_threshold:
                        self._identical_frame_streak += 1
                    else:
                        self._identical_frame_streak = 0
                self._last_frame_signature = signature

                if self._identical_frame_streak >= self.config.max_identical_frames:
                    self._stream_state = "frozen"
                    self._force_reconnect()
                    return

            packet: FramePacket = (self.config.camera_id, timestamp, frame.copy())
            self._last_packet = packet
            self._buffer.append(packet)
            self._total_frames_read += 1
            self._last_successful_frame_ts = timestamp
            self._stream_state = "running"

    def _frame_signature(self, frame: np.ndarray) -> float:
        small = cv2.resize(frame, (32, 18), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    def _force_reconnect(self) -> None:
        self._release_capture()
        self._stream_state = "reconnecting"

    def _release_capture(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def get_latest_packet(self) -> Optional[FramePacket]:
        with self._lock:
            if self._last_packet is None:
                return None
            cam_id, ts, frame = self._last_packet
            return cam_id, ts, frame.copy()

    def get_buffer_snapshot(self) -> List[FramePacket]:
        with self._lock:
            return [(cam_id, ts, frame.copy()) for cam_id, ts, frame in self._buffer]

    def get_packets_between(self, start_ts: float, end_ts: float) -> List[FramePacket]:
        with self._lock:
            return [
                (cam_id, ts, frame.copy())
                for cam_id, ts, frame in self._buffer
                if start_ts <= ts <= end_ts
            ]

    def get_nearest_packet(self, reference_ts: float, tolerance_ms: float) -> Optional[FramePacket]:
        tolerance_s = tolerance_ms / 1000.0
        with self._lock:
            if not self._buffer:
                return None

            best_packet = None
            best_dt = None
            for cam_id, ts, frame in self._buffer:
                dt = abs(ts - reference_ts)
                if dt <= tolerance_s and (best_dt is None or dt < best_dt):
                    best_dt = dt
                    best_packet = (cam_id, ts, frame.copy())
            return best_packet

    def get_health_status(self) -> str:
        with self._lock:
            now = time.time()

            if not self._running:
                return "stopped"

            if self._stream_state in {"opening", "warming", "reconnecting"}:
                return "recovering"

            if self._last_successful_frame_ts is None:
                return "no_signal"

            age = now - self._last_successful_frame_ts
            if age > self.config.healthcheck_down_after_seconds:
                return "down"

            if self._stream_state in {"degraded", "read_failed", "frozen"}:
                return "degraded"

            return "healthy"

    def stats(self) -> CameraRuntimeStats:
        with self._lock:
            frame_shape = None if self._last_packet is None else self._last_packet[2].shape
            last_ts = None if self._last_packet is None else self._last_packet[1]
            is_open = self.cap is not None and self.cap.isOpened()

            return CameraRuntimeStats(
                camera_id=self.config.camera_id,
                name=self.config.name,
                is_open=is_open,
                is_running=self._running,
                total_frames_read=self._total_frames_read,
                dropped_frames=self._dropped_frames,
                buffer_size=len(self._buffer),
                last_timestamp=last_ts,
                frame_shape=frame_shape,
                consecutive_read_failures=self._consecutive_read_failures,
                reconnect_count=self._reconnect_count,
                identical_frame_streak=self._identical_frame_streak,
                stream_state=self._stream_state,
                health_status=self.get_health_status(),
            )
class AppContext:
    def __init__(self, config):
        self.config = config
        self.camera_manager = CameraManager(config["cameras"])

class CameraManager:
    def __init__(self, camera_configs: List[CameraSourceConfig]):
        camera_ids = [cfg.camera_id for cfg in camera_configs]
        if len(set(camera_ids)) != len(camera_ids):
            raise ValueError("camera_id duplicado na configuração.")

        self._streams: Dict[int, CameraStream] = {
            cfg.camera_id: CameraStream(cfg)
            for cfg in camera_configs
            if cfg.enabled
        }

    def start_all(self) -> None:
        for stream in self._streams.values():
            stream.start()

    def stop_all(self) -> None:
        for stream in self._streams.values():
            stream.stop()

    def stream(self, camera_id: int) -> CameraStream:
        if camera_id not in self._streams:
            raise KeyError(f"Câmara não encontrada: {camera_id}")
        return self._streams[camera_id]

    def enabled_camera_ids(self) -> List[int]:
        return sorted(self._streams.keys())

    def latest_packets(self) -> Dict[int, FramePacket]:
        output: Dict[int, FramePacket] = {}
        for camera_id, stream in self._streams.items():
            packet = stream.get_latest_packet()
            if packet is not None:
                output[camera_id] = packet
        return output

    def get_synchronized_packets(self, tolerance_ms: float = 25.0) -> Dict[int, FramePacket]:
        latest = self.latest_packets()
        if not latest:
            return {}

        reference_ts = max(packet[1] for packet in latest.values())
        synchronized: Dict[int, FramePacket] = {}

        for camera_id, stream in self._streams.items():
            if stream.get_health_status() not in {"healthy", "degraded", "recovering"}:
                continue
            packet = stream.get_nearest_packet(reference_ts, tolerance_ms=tolerance_ms)
            if packet is not None:
                synchronized[camera_id] = packet

        return synchronized

    def all_buffers_snapshot(self) -> Dict[int, List[FramePacket]]:
        return {
            camera_id: stream.get_buffer_snapshot()
            for camera_id, stream in self._streams.items()
        }

    def get_time_window_packets(
        self,
        start_ts: float,
        end_ts: float,
    ) -> Dict[int, List[FramePacket]]:
        return {
            camera_id: stream.get_packets_between(start_ts, end_ts)
            for camera_id, stream in self._streams.items()
        }

    def stats(self) -> List[CameraRuntimeStats]:
        return [self._streams[camera_id].stats() for camera_id in sorted(self._streams.keys())]

    def health_summary(self) -> Dict[int, str]:
        return {
            camera_id: self._streams[camera_id].get_health_status()
            for camera_id in sorted(self._streams.keys())
        }

    def wait_until_ready(
        self,
        min_cameras: int = 1,
        timeout_seconds: float = 10.0,
    ) -> bool:
        started = time.time()
        while time.time() - started < timeout_seconds:
            healthy = 0
            for camera_id in self.enabled_camera_ids():
                status = self.stream(camera_id).get_health_status()
                if status in {"healthy", "degraded"}:
                    packet = self.stream(camera_id).get_latest_packet()
                    if packet is not None:
                        healthy += 1
            if healthy >= min_cameras:
                return True
            time.sleep(0.05)
        return False
    def get_preview_frame(self, camera_id=None):
        """
        Retorna o frame BGR mais recente.
        Se camera_id for None, devolve o da primeira câmara disponível.
        """
        latest = self.latest_packets()
        if camera_id is not None and camera_id in latest:
            frame = latest[camera_id][2]
            if frame is not None and frame.size > 0:
                return frame
            return None
        # Primeira câmara disponível
        for frame_packet in latest.values():
            frame = frame_packet[2]
            if frame is not None and frame.size > 0:
                return frame
        return None

        