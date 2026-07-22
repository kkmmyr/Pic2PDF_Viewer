import numpy as np

from novel_capturer import NovelKindleCapturer


def _capturer() -> NovelKindleCapturer:
    capturer = NovelKindleCapturer()
    capturer.config.SIDE_IGNORE_PX = 100
    capturer.config.DETECTION_PADDING_PX = 10
    capturer.config.MIN_CROP_WIDTH_RATIO = 0.9
    return capturer


def test_blank_scan_rows_do_not_override_detected_edges():
    image = np.full((600, 1000, 3), 255, dtype=np.uint8)
    image[20:480, 110:890] = 0
    capturer = _capturer()

    capturer._detect_boundaries(image, 1000, 600)

    assert (capturer.config.CROP_X1, capturer.config.CROP_X2) == (100, 900)


def test_narrow_page_falls_back_to_safe_width():
    image = np.full((600, 1000, 3), 255, dtype=np.uint8)
    image[20:580, 400:600] = 0
    capturer = _capturer()

    capturer._detect_boundaries(image, 1000, 600)

    assert (capturer.config.CROP_X1, capturer.config.CROP_X2) == (90, 910)


def test_all_white_page_falls_back_to_safe_width():
    image = np.full((600, 1000, 3), 255, dtype=np.uint8)
    capturer = _capturer()

    capturer._detect_boundaries(image, 1000, 600)

    assert (capturer.config.CROP_X1, capturer.config.CROP_X2) == (90, 910)
