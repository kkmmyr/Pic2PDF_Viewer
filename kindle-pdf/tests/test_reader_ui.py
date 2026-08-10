from __future__ import annotations

from types import SimpleNamespace

import pytest

from kindle_controller.models import ControllerConfig, KindleControllerError
from kindle_controller.reader_policy import PageLayoutPolicy
from kindle_controller.reader_ui import ReaderUIAdapter


class _ValuePattern:
    def __init__(self, value: str = "") -> None:
        self.Value = value

    def SetValue(self, value: str) -> None:
        self.Value = value


class _Control:
    def __init__(self, automation_id: str, *, selected: bool = False) -> None:
        self.AutomationId = automation_id
        self.Element = SimpleNamespace(on=selected)
        self.value_pattern = _ValuePattern()

    def GetValuePattern(self) -> _ValuePattern:
        return self.value_pattern


class _Host:
    def __init__(self) -> None:
        self.config = ControllerConfig(control_timeout_seconds=0.01)
        self.controls: dict[str, _Control] = {
            "ReadingArea": _Control("ReadingArea"),
            "aaMenuButton": _Control("aaMenuButton"),
            "CloseSideMenuHeaderButton": _Control("CloseSideMenuHeaderButton"),
        }
        self.clicked: list[str] = []

    def _control_by_id(self, automation_id: str, **_kwargs: object) -> object | None:
        return self.controls.get(automation_id)

    def _edit_by_id(self, automation_id: str, **_kwargs: object) -> object | None:
        return self.controls.get(automation_id)

    def _button_by_id(self, automation_id: str, **_kwargs: object) -> object | None:
        return self.controls.get(automation_id)

    def _click_control(self, control: object) -> None:
        typed_control = control
        self.clicked.append(typed_control.AutomationId)  # type: ignore[attr-defined]

    def _click_relative_to_control(
        self,
        _control: object,
        *,
        x_offset: int,
        y_offset: int,
    ) -> bool:
        return (x_offset, y_offset) == (-30, 45)

    @staticmethod
    def _toggle_is_on(control: object) -> bool:
        return bool(control.Element.on)  # type: ignore[attr-defined]


def test_layout_adapter_accepts_declared_compatibility_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _Host()
    host.controls["フォント-item"] = _Control("フォント-item")
    monkeypatch.setattr("kindle_controller.reader_ui.time.sleep", lambda _value: None)

    ReaderUIAdapter(host).apply_page_layout(
        PageLayoutPolicy(
            option_id="aaOption-Single",
            compatible_without_option_id="フォント-item",
        )
    )

    assert host.clicked == ["aaMenuButton", "CloseSideMenuHeaderButton", "ReadingArea"]


def test_layout_adapter_fails_closed_when_option_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _Host()
    monkeypatch.setattr("kindle_controller.reader_ui.time.sleep", lambda _value: None)

    with pytest.raises(KindleControllerError) as exc:
        ReaderUIAdapter(host).apply_page_layout(
            PageLayoutPolicy(option_id="aaOption-Split")
        )

    assert exc.value.error_code == "positioning_failed"
    assert host.clicked == ["aaMenuButton", "CloseSideMenuHeaderButton", "ReadingArea"]


def test_location_value_requires_value_pattern_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _Host()
    location_input = _Control("go-to-page-input")
    host.controls["go-to-page-input"] = location_input
    monkeypatch.setattr("kindle_controller.reader_ui.time.sleep", lambda _value: None)

    adapter = ReaderUIAdapter(host)
    assert adapter.set_location_value("1")

    location_input.value_pattern.SetValue = lambda _value: None  # type: ignore[method-assign]
    location_input.value_pattern.Value = "stale"
    assert not adapter.set_location_value("1")
