from __future__ import annotations

import pytest

from kindle_platform import (
    IS_WINDOWS,
    KindlePlatformUnavailableError,
    require_windows_runtime,
    windll,
)


@pytest.mark.skipif(IS_WINDOWS, reason="Windows実機境界は利用可能")
def test_non_windows_runtime_guard_fails_closed() -> None:
    with pytest.raises(KindlePlatformUnavailableError, match="requires.*Windows"):
        require_windows_runtime("Kindle controller")


@pytest.mark.skipif(IS_WINDOWS, reason="Windowsでは実際のuser32を使用する")
def test_unmocked_win32_call_fails_closed() -> None:
    with pytest.raises(KindlePlatformUnavailableError, match="user32"):
        windll.user32.GetForegroundWindow()
