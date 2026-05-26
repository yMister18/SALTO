import numpy as np
import cv2

from image_quality import ImageQualityAnalyzer


def test_image_quality_detects_low_contrast():
    frame = np.full((200, 300, 3), 128, dtype=np.uint8)
    analyzer = ImageQualityAnalyzer()
    result = analyzer.analyze(frame)
    assert result.is_low_contrast is True


def test_image_quality_detects_sharp_pattern_better_than_flat():
    flat = np.full((200, 300, 3), 128, dtype=np.uint8)

    sharp = np.full((200, 300, 3), 128, dtype=np.uint8)
    cv2.line(sharp, (0, 0), (299, 199), (255, 255, 255), 3)
    cv2.line(sharp, (299, 0), (0, 199), (0, 0, 0), 3)

    analyzer = ImageQualityAnalyzer()
    flat_result = analyzer.analyze(flat)
    sharp_result = analyzer.analyze(sharp)

    assert sharp_result.sharpness_variance > flat_result.sharpness_variance