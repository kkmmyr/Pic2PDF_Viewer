"""正式撮影前にページ送り・撮影矩形を短時間検証するカナリア。"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

import cv2
import numpy as np


class CaptureCanaryError(RuntimeError):
    """正式撮影を開始してはならないカナリア失敗。"""


@dataclass(frozen=True)
class CaptureCanaryResult:
    policy_version: str
    passed: bool
    dimensions: tuple[int, int]
    crop_bounds: tuple[int, int, int, int]
    first_sha256: str
    second_sha256: str
    mean_difference: float
    changed_ratio: float

    def to_manifest(self) -> dict:
        return asdict(self)


def _image_digest(image: np.ndarray) -> str:
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise CaptureCanaryError("カナリア画像をエンコードできません")
    return hashlib.sha256(encoded.tobytes()).hexdigest()


def run_capture_canary(capturer) -> CaptureCanaryResult:
    crop = (
        int(capturer.config.CROP_X1),
        int(capturer.config.CROP_Y1),
        int(capturer.config.CROP_X2),
        int(capturer.config.CROP_Y2),
    )
    if crop[0] >= crop[2] or crop[1] >= crop[3]:
        raise CaptureCanaryError("カナリアの撮影矩形が不正です")
    first = capturer._wait_for_stable_page(None)
    if first is None:
        raise CaptureCanaryError("カナリアの先頭画面を取得できません")
    capturer._next_page()
    second = capturer._wait_for_stable_page(first)
    if second is None:
        raise CaptureCanaryError("カナリアでページ送り後の変化を確認できません")
    if first.shape != second.shape:
        raise CaptureCanaryError("カナリア画像の寸法が一致しません")
    if capturer._images_visually_equal(first, second):
        raise CaptureCanaryError("カナリアの2画面が視覚的に同一です")

    height, width = first.shape[:2]
    if (crop[2] - crop[0], crop[3] - crop[1]) != (width, height):
        raise CaptureCanaryError("カナリア画像と撮影矩形の寸法が一致しません")
    difference = cv2.absdiff(first, second)
    channel_means = cv2.mean(difference)[:3]
    mean_difference = float(sum(channel_means) / len(channel_means))
    gray_difference = cv2.cvtColor(difference, cv2.COLOR_BGR2GRAY)
    changed_ratio = float(
        np.mean(gray_difference > capturer.config.PAGE_VISUAL_PIXEL_THRESHOLD)
    )
    return CaptureCanaryResult(
        policy_version="kindle-capture-canary-v1",
        passed=True,
        dimensions=(width, height),
        crop_bounds=crop,
        first_sha256=_image_digest(first),
        second_sha256=_image_digest(second),
        mean_difference=round(mean_difference, 6),
        changed_ratio=round(changed_ratio, 9),
    )
