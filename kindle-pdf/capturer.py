"""既存importを維持するKindle capturer facade。"""

import time
from typing import TYPE_CHECKING

from PIL import ImageGrab

from capture_base import Config, KindleCapturer
from capture_loop import CaptureReport, CaptureResult
from comic_capturer import AutoConfig, AutoKindleCapturer
from kindle_platform import pyautogui as pag, windll

if TYPE_CHECKING:
    from capture_ui import BookInfoDialog

_COMPATIBILITY_EXPORTS = (time, windll, pag, ImageGrab)


def __getattr__(name: str) -> object:
    if name == "BookInfoDialog":
        from capture_ui import BookInfoDialog

        return BookInfoDialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AutoConfig",
    "AutoKindleCapturer",
    "BookInfoDialog",
    "Config",
    "CaptureReport",
    "CaptureResult",
    "KindleCapturer",
]
