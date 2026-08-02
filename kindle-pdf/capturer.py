"""既存importを維持するKindle capturer facade。"""

import time
from ctypes import windll

import pyautogui as pag
from PIL import ImageGrab

from capture_base import Config, KindleCapturer
from capture_loop import CaptureReport, CaptureResult
from capture_ui import BookInfoDialog
from comic_capturer import AutoConfig, AutoKindleCapturer

_COMPATIBILITY_EXPORTS = (time, windll, pag, ImageGrab)

__all__ = [
    "AutoConfig",
    "AutoKindleCapturer",
    "BookInfoDialog",
    "Config",
    "CaptureReport",
    "CaptureResult",
    "KindleCapturer",
]
