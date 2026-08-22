"""Kindle操作が使うOS / desktop APIのimport境界。"""

from __future__ import annotations

import ctypes
import sys
from typing import NoReturn

IS_WINDOWS = sys.platform == "win32"


class KindlePlatformUnavailableError(RuntimeError):
    """現在のOSまたはdesktop sessionで実機APIを利用できない。"""


def require_windows_runtime(component: str = "Kindle automation") -> None:
    """Windows実機だけで実行可能な処理をfail closedにする。"""
    if not IS_WINDOWS:
        raise KindlePlatformUnavailableError(
            f"{component} requires an unlocked Windows desktop session",
        )


class _UnavailableAPI:
    """Importは許し、未モックの実呼び出しだけを拒否する。"""

    def __init__(self, component: str, detail: str) -> None:
        self._component = component
        self._detail = detail

    def __getattr__(self, attribute: str):
        def unavailable(*_args: object, **_kwargs: object) -> NoReturn:
            raise KindlePlatformUnavailableError(
                f"{self._component}.{attribute} is unavailable: {self._detail}",
            )

        return unavailable


if IS_WINDOWS:
    from _ctypes import COMError

    import uiautomation as auto

    WINFUNCTYPE = ctypes.WINFUNCTYPE
    windll = ctypes.windll
else:

    class COMError(Exception):
        """Windows外のtest doubleがCOM失敗契約を再現するための例外。"""

    class _PropertyId:
        ToggleToggleStateProperty = 30086

    class _ToggleState:
        On = 1

    class _UnavailableAutomation(_UnavailableAPI):
        PropertyId = _PropertyId
        ToggleState = _ToggleState

    WINFUNCTYPE = ctypes.CFUNCTYPE
    windll = _UnavailableAPI(
        "ctypes.windll",
        "Win32 APIs require Windows",
    )
    windll.user32 = _UnavailableAPI(
        "ctypes.windll.user32",
        "Win32 APIs require Windows",
    )
    windll.kernel32 = _UnavailableAPI(
        "ctypes.windll.kernel32",
        "Win32 APIs require Windows",
    )
    auto = _UnavailableAutomation(
        "uiautomation",
        "Windows UI Automation requires Windows",
    )

try:
    import pyautogui as pyautogui
except Exception as import_error:
    pyautogui = _UnavailableAPI(
        "pyautogui",
        f"desktop input is unavailable ({type(import_error).__name__})",
    )


__all__ = [
    "COMError",
    "IS_WINDOWS",
    "KindlePlatformUnavailableError",
    "WINFUNCTYPE",
    "auto",
    "pyautogui",
    "require_windows_runtime",
    "windll",
]
