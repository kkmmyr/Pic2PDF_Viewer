from ctypes.wintypes import RECT

import numpy as np
import pytest
from PIL import Image

from novel_capturer import NovelKindleCapturer


def _capturer():
    capturer = NovelKindleCapturer()
    capturer.rect = RECT(100, 200, 1100, 1000)
    capturer.config.CROP_X1 = 20
    capturer.config.CROP_X2 = 980
    capturer.config.CROP_Y1 = 48
    capturer.config.CROP_Y2 = 760
    capturer.configure_cover_frame((100, 300, 1100, 900))
    return capturer


def test_cover_retains_both_edges_and_body_retains_pixels(tmp_path):
    capturer = _capturer()
    frame = np.zeros((712, 960, 3), dtype=np.uint8)
    frame[0] = (10, 20, 30)
    frame[-1] = (40, 50, 60)
    frame[52:652] = (70, 80, 90)
    capturer._save_image(frame, str(tmp_path / "001.png"))
    capturer._save_image(frame, str(tmp_path / "002.png"))
    cover = np.array(Image.open(tmp_path / "001.png"))[:, :, ::-1]
    body = np.array(Image.open(tmp_path / "002.png"))[:, :, ::-1]
    assert np.array_equal(cover, frame)
    assert cover.shape == body.shape == (712, 960, 3)
    assert np.array_equal(body[52:652], frame[52:652])
    assert np.all(body[:52] == 255) and np.all(body[652:] == 255)
    assert np.array_equal(frame[0, 0], [10, 20, 30])


def test_chrome_changes_do_not_count_as_page_turns():
    capturer = _capturer()
    first = np.zeros((712, 960, 3), dtype=np.uint8)
    changed = first.copy()
    changed[:52] = 255
    changed[652:] = 255
    assert capturer._images_visually_equal(first, changed)
    changed[100:300] = 128
    assert not capturer._images_visually_equal(first, changed)


def test_frame_size_change_is_not_hidden_by_body_comparison():
    capturer = _capturer()
    first = np.zeros((712, 960, 3), dtype=np.uint8)
    resized = np.zeros((713, 960, 3), dtype=np.uint8)
    assert not capturer._images_visually_equal(first, resized)


@pytest.mark.parametrize(
    "bounds",
    [
        (100, 240, 1100, 900),
        (100, 300, 1100, 980),
        (100, 900, 1100, 300),
        (130, 300, 1100, 900),
    ],
)
def test_invalid_body_bounds_fail_closed(bounds):
    capturer = _capturer()
    with pytest.raises(RuntimeError):
        capturer.configure_cover_frame(bounds)


def test_manual_capture_does_not_add_padding(tmp_path):
    capturer = NovelKindleCapturer()
    frame = np.zeros((12, 15, 3), dtype=np.uint8)
    capturer._save_image(frame, str(tmp_path / "002.png"))
    assert np.array_equal(np.array(Image.open(tmp_path / "002.png")), frame)
