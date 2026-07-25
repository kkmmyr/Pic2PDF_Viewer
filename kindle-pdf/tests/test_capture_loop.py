from ctypes.wintypes import RECT

import numpy as np
import pytest

import capturer as capturer_module
from capturer import AutoKindleCapturer, KindleCapturer


def _image(value: int) -> np.ndarray:
    return np.full((4, 4, 3), value, dtype=np.uint8)


def test_new_kindle_page_turn_uses_selected_arrow_key(monkeypatch):
    capturer = KindleCapturer()
    capturer._new_kindle_mode = True
    capturer.rect = RECT(100, 200, 1100, 1000)
    capturer.config.PAGE_TURN_WAIT = 0
    key_events = []

    monkeypatch.setattr(
        capturer_module.pag,
        "keyDown",
        lambda key: key_events.append(("down", key)),
    )
    monkeypatch.setattr(
        capturer_module.pag,
        "keyUp",
        lambda key: key_events.append(("up", key)),
    )
    monkeypatch.setattr(capturer_module.time, "sleep", lambda _seconds: None)

    capturer.config.PAGE_CHANGE_KEY = "left"
    capturer._next_page()
    capturer.config.PAGE_CHANGE_KEY = "right"
    capturer._next_page()

    assert key_events == [
        ("down", "left"),
        ("up", "left"),
        ("down", "right"),
        ("up", "right"),
    ]


def test_visual_page_comparison_ignores_small_ui_overlay():
    capturer = KindleCapturer()
    page = np.zeros((100, 100, 3), dtype=np.uint8)
    tiny_overlay = page.copy()
    tiny_overlay[0, 0] = 255
    changed_page = np.full((100, 100, 3), 2, dtype=np.uint8)

    assert capturer._images_visually_equal(page, tiny_overlay)
    assert not capturer._images_visually_equal(page, changed_page)


def test_wait_for_stable_page_skips_transient_frame(monkeypatch):
    capturer = KindleCapturer()
    capturer.config.WAIT_SEC = 0
    capturer.config.PAGE_STABLE_SEC = 0
    capturer.config.TIMEOUT_SEC = 1
    previous = _image(10)
    transient = _image(255)
    final = _image(20)
    images = iter([previous, transient, final, final])

    monkeypatch.setattr(capturer, "_capture_screen", lambda: next(images))
    monkeypatch.setattr(capturer_module.time, "sleep", lambda _seconds: None)

    result = capturer._wait_for_stable_page(previous)

    assert np.array_equal(result, final)


def test_capture_loop_stops_at_expected_count(tmp_path, monkeypatch):
    capturer = KindleCapturer()
    capturer.hwnd = 1
    capturer.config.IMG_OUTPUT_DIR = str(tmp_path)
    capturer.config.EXPECTED_PAGES = 2
    pages = iter([_image(1), _image(2)])
    saved = []
    page_turns = []

    monkeypatch.setattr(
        capturer_module.windll.user32, "SetForegroundWindow", lambda _hwnd: 1
    )
    monkeypatch.setattr(capturer_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(capturer, "_wait_for_stable_page", lambda _old: next(pages))
    monkeypatch.setattr(
        capturer, "_save_image", lambda image, path: saved.append((image, path))
    )
    monkeypatch.setattr(capturer, "_next_page", lambda: page_turns.append(True))

    total, _save_dir = capturer.capture_loop("book")

    assert total == 2
    assert [path.rsplit("\\", 1)[-1] for _image_value, path in saved] == [
        "001.png",
        "002.png",
    ]
    assert len(page_turns) == 1


def test_capture_loop_reports_saved_page_progress(tmp_path, monkeypatch):
    capturer = KindleCapturer()
    capturer.hwnd = 1
    capturer.config.IMG_OUTPUT_DIR = str(tmp_path)
    capturer.config.EXPECTED_PAGES = 2
    pages = iter([_image(1), _image(2)])
    progress = []

    monkeypatch.setattr(
        capturer_module.windll.user32, "SetForegroundWindow", lambda _hwnd: 1
    )
    monkeypatch.setattr(capturer_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(capturer, "_wait_for_stable_page", lambda _old: next(pages))
    monkeypatch.setattr(capturer, "_save_image", lambda _image, _path: None)
    monkeypatch.setattr(capturer, "_next_page", lambda: None)

    total, _save_dir = capturer.capture_loop("book", on_page=progress.append)

    assert total == 2
    assert progress == [1, 2]


def test_capture_loop_rejects_early_stop_before_expected_count(tmp_path, monkeypatch):
    capturer = KindleCapturer()
    capturer.hwnd = 1
    capturer.config.IMG_OUTPUT_DIR = str(tmp_path)
    capturer.config.EXPECTED_PAGES = 2
    capturer.config.PAGE_CHANGE_RETRY_COUNT = 0
    pages = iter([_image(1), None])

    monkeypatch.setattr(
        capturer_module.windll.user32, "SetForegroundWindow", lambda _hwnd: 1
    )
    monkeypatch.setattr(capturer_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(capturer, "_wait_for_stable_page", lambda _old: next(pages))
    monkeypatch.setattr(capturer, "_save_image", lambda _image_value, _path: None)
    monkeypatch.setattr(capturer, "_next_page", lambda: None)

    with pytest.raises(RuntimeError, match="1/2"):
        capturer.capture_loop("book")


def test_new_kindle_restores_preexisting_fullscreen_on_cleanup(monkeypatch):
    capturer = AutoKindleCapturer()
    capturer.hwnd = 1
    window_rect = RECT(0, 0, 1200, 900)
    pressed_keys = []

    monkeypatch.setattr(capturer, "_get_window_title", lambda: "Kindle")
    monkeypatch.setattr(capturer, "_is_fullscreen", lambda: True)
    monkeypatch.setattr(capturer, "_get_window_rect", lambda: window_rect)
    monkeypatch.setattr(
        capturer, "_detect_boundaries", lambda _image, _width, _height: None
    )
    monkeypatch.setattr(capturer_module.ImageGrab, "grab", lambda **_kwargs: _image(0))
    monkeypatch.setattr(capturer_module.pag, "press", pressed_keys.append)
    monkeypatch.setattr(capturer_module.pag, "moveTo", lambda *_args: None)
    monkeypatch.setattr(capturer_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        capturer_module.windll.user32, "SetForegroundWindow", lambda _hwnd: 1
    )
    monkeypatch.setattr(capturer_module.windll.user32, "IsZoomed", lambda _hwnd: 0)
    monkeypatch.setattr(
        capturer_module.windll.user32, "ShowWindow", lambda _hwnd, _command: 1
    )

    capturer.setup_window()
    capturer.cleanup()

    assert pressed_keys == ["f11", "f11"]
    assert capturer._restore_fullscreen_on_cleanup is False
