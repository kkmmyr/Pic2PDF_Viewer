from __future__ import annotations

import os
import os.path as osp
from typing import Protocol

import cv2
import numpy as np
from PIL import ImageGrab


class CaptureBoundsConfig(Protocol):
    CROP_X1: int
    CROP_Y1: int
    CROP_X2: int
    CROP_Y2: int


class WindowRect(Protocol):
    left: int
    top: int


def prepare_image_dir(output_dir: str, title: str) -> str:
    save_dir = osp.join(output_dir, title)
    os.makedirs(save_dir, exist_ok=True)
    return save_dir


def capture_screen(rect: WindowRect, config: CaptureBoundsConfig) -> np.ndarray:
    image = ImageGrab.grab(
        bbox=(
            rect.left + config.CROP_X1,
            rect.top + config.CROP_Y1,
            rect.left + config.CROP_X2,
            rect.top + config.CROP_Y2,
        ),
        all_screens=True,
    )
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def save_png(image: np.ndarray, filepath: str) -> None:
    try:
        is_success, encoded = cv2.imencode(".png", image)
        if not is_success:
            raise RuntimeError(f"Failed to encode image: {filepath}")
        encoded.tofile(filepath)
    except Exception as exc:
        raise RuntimeError(f"Failed to save image {filepath}: {exc}") from exc
