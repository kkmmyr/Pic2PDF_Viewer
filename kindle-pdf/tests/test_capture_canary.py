from types import SimpleNamespace

import numpy as np
import pytest

from capture_canary import CaptureCanaryError, run_capture_canary


class _Capturer:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.turns = 0
        self.config = SimpleNamespace(
            CROP_X1=0,
            CROP_Y1=0,
            CROP_X2=20,
            CROP_Y2=30,
            PAGE_VISUAL_PIXEL_THRESHOLD=20,
        )

    def _wait_for_stable_page(self, _previous):
        return next(self.pages)

    def _next_page(self):
        self.turns += 1

    def _images_visually_equal(self, left, right):
        return np.array_equal(left, right)


def _image(value: int, *, width=20, height=30):
    return np.full((height, width, 3), value, dtype=np.uint8)


def test_canary_records_two_distinct_pages() -> None:
    capturer = _Capturer([_image(1), _image(200)])

    result = run_capture_canary(capturer)

    assert result.passed
    assert result.dimensions == (20, 30)
    assert result.first_sha256 != result.second_sha256
    assert result.changed_ratio == 1.0
    assert capturer.turns == 1


def test_canary_rejects_page_turn_without_change() -> None:
    capturer = _Capturer([_image(1), None])

    with pytest.raises(CaptureCanaryError, match="変化"):
        run_capture_canary(capturer)


def test_canary_rejects_dimension_change() -> None:
    capturer = _Capturer([_image(1), _image(2, width=21)])

    with pytest.raises(CaptureCanaryError, match="寸法"):
        run_capture_canary(capturer)


def test_canary_rejects_crop_mismatch() -> None:
    capturer = _Capturer([_image(1), _image(2)])
    capturer.config.CROP_X2 = 19

    with pytest.raises(CaptureCanaryError, match="撮影矩形"):
        run_capture_canary(capturer)
