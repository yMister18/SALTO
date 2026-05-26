from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ImageQualityThresholds:
    min_sharpness_variance: float = 80.0
    min_contrast_std: float = 18.0
    min_brightness_mean: float = 45.0
    max_brightness_mean: float = 210.0
    min_dynamic_range: float = 50.0


@dataclass(frozen=True)
class ImageQualityResult:
    sharpness_variance: float
    contrast_std: float
    brightness_mean: float
    dynamic_range: float
    is_blurry: bool
    is_too_dark: bool
    is_too_bright: bool
    is_low_contrast: bool
    passed: bool


class ImageQualityAnalyzer:
    def __init__(self, thresholds: ImageQualityThresholds | None = None) -> None:
        self.thresholds = thresholds or ImageQualityThresholds()

    def analyze(self, frame: np.ndarray) -> ImageQualityResult:
        if frame is None or frame.size == 0:
            raise ValueError("Frame inválido para análise de qualidade.")

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sharpness_variance = float(laplacian.var())

        brightness_mean = float(np.mean(gray))
        contrast_std = float(np.std(gray))
        dynamic_range = float(np.percentile(gray, 95) - np.percentile(gray, 5))

        is_blurry = sharpness_variance < self.thresholds.min_sharpness_variance
        is_too_dark = brightness_mean < self.thresholds.min_brightness_mean
        is_too_bright = brightness_mean > self.thresholds.max_brightness_mean
        is_low_contrast = (
            contrast_std < self.thresholds.min_contrast_std
            or dynamic_range < self.thresholds.min_dynamic_range
        )

        passed = not any([is_blurry, is_too_dark, is_too_bright, is_low_contrast])

        return ImageQualityResult(
            sharpness_variance=sharpness_variance,
            contrast_std=contrast_std,
            brightness_mean=brightness_mean,
            dynamic_range=dynamic_range,
            is_blurry=is_blurry,
            is_too_dark=is_too_dark,
            is_too_bright=is_too_bright,
            is_low_contrast=is_low_contrast,
            passed=passed,
        )

    def draw_overlay(
        self,
        frame: np.ndarray,
        result: ImageQualityResult,
    ) -> np.ndarray:
        output = frame.copy()

        box_w = 620
        box_h = 170
        cv2.rectangle(output, (24, 24), (24 + box_w, 24 + box_h), (0, 0, 0), -1)

        status = "QUALITY OK" if result.passed else "QUALITY WARNING"
        color = (0, 255, 0) if result.passed else (0, 165, 255)

        lines = [
            status,
            f"Sharpness variance: {result.sharpness_variance:.2f}",
            f"Contrast std: {result.contrast_std:.2f}",
            f"Brightness mean: {result.brightness_mean:.2f}",
            f"Dynamic range: {result.dynamic_range:.2f}",
            self._build_flags_line(result),
        ]

        y = 52
        for idx, line in enumerate(lines):
            line_color = color if idx == 0 else (255, 255, 255)
            cv2.putText(
                output,
                line,
                (40, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                line_color,
                2,
                cv2.LINE_AA,
            )
            y += 24

        return output

    def _build_flags_line(self, result: ImageQualityResult) -> str:
        flags = []
        if result.is_blurry:
            flags.append("blurry")
        if result.is_too_dark:
            flags.append("too_dark")
        if result.is_too_bright:
            flags.append("too_bright")
        if result.is_low_contrast:
            flags.append("low_contrast")
        if not flags:
            flags.append("none")
        return "Flags: " + ", ".join(flags)