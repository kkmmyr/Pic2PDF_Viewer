"""Test doubles for Kindle app layout, location, and download controls."""

from types import SimpleNamespace

from kindle_app_controller import ControllerConfig, KindleAppController


class _Button:
    def __init__(self, name: str) -> None:
        self.Name = name
        self.clicked = False

    def Click(self, **_kwargs) -> None:
        self.clicked = True


class _ToggleElement:
    def __init__(self, on: bool) -> None:
        self.on = on

    def GetCurrentPropertyValue(self, _property_id: int) -> int:
        return int(self.on)


class _LayoutControl:
    def __init__(self, automation_id: str, *, on: bool = False) -> None:
        self.AutomationId = automation_id
        self.Element = _ToggleElement(on)
        self.BoundingRectangle = SimpleNamespace(
            left=10,
            top=20,
            right=110,
            bottom=60,
        )


class _DownloadController(KindleAppController):
    def __init__(
        self,
        controls: list[_Button | None],
        snapshots: list[tuple[int, int, int] | None],
        config: ControllerConfig,
    ) -> None:
        super().__init__(config)
        self.controls = controls
        self.snapshots = snapshots

    def _control_by_id(self, *_args, **_kwargs):
        if len(self.controls) > 1:
            return self.controls.pop(0)
        return self.controls[0]

    def _content_snapshot(self, _asin: str):
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    def _ensure_process_running(self) -> None:
        return None

    def _click_control(self, control: _Button) -> None:
        control.clicked = True


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _PositionController(KindleAppController):
    def _ensure_process_running(self) -> None:
        return None

    def _try_go_to_location_start(
        self,
        source: str,
        *,
        direction: str = "left",
        on_poll=None,
    ) -> bool:
        del source, direction, on_poll
        return False


class _LayoutController(KindleAppController):
    def __init__(self) -> None:
        super().__init__(ControllerConfig(control_timeout_seconds=0.2))
        self.controls = {
            "ReadingArea": _LayoutControl("ReadingArea"),
            "aaMenuButton": _LayoutControl("aaMenuButton"),
            "aaOption-Split": _LayoutControl("aaOption-Split"),
            "aaOption-Single": _LayoutControl("aaOption-Single", on=True),
            "CloseSideMenuHeaderButton": _LayoutControl("CloseSideMenuHeaderButton"),
        }
        self.clicked: list[str] = []

    def _control_by_id(self, automation_id: str, **_kwargs):
        return self.controls.get(automation_id)

    def _click_control(self, control: _LayoutControl) -> None:
        self.clicked.append(control.AutomationId)
        if control.AutomationId == "aaOption-Split":
            self.controls["aaOption-Split"].Element.on = True
            self.controls["aaOption-Single"].Element.on = False
        elif control.AutomationId == "aaOption-Single":
            self.controls["aaOption-Split"].Element.on = False
            self.controls["aaOption-Single"].Element.on = True


class _LocationControl(_LayoutControl):
    def __init__(
        self,
        automation_id: str,
        *,
        name: str = "",
        value: str = "",
    ) -> None:
        super().__init__(automation_id)
        self.Name = name
        self.value_pattern = _LocationValuePattern(value)
        self.focused = False

    def SetFocus(self) -> None:
        self.focused = True

    def GetValuePattern(self):
        return self.value_pattern


class _LocationValuePattern:
    def __init__(self, value: str) -> None:
        self.Value = value

    def SetValue(self, value: str) -> None:
        self.Value = value


class _LocationController(KindleAppController):
    def __init__(self, footer_name: str) -> None:
        super().__init__(ControllerConfig(control_timeout_seconds=0.2))
        self.controls = {
            "ReadingArea": _LocationControl("ReadingArea"),
            "moreMenuButton": _LocationControl(
                "moreMenuButton",
                name="もっと",
            ),
            "go-to-page-input": _LocationControl(
                "go-to-page-input",
                name="ロケーション番号入力",
            ),
            "FooterLabelText": _LocationControl(
                "FooterLabelText",
                name=footer_name,
            ),
        }
        self.named_controls = {
            ("ページへ移動する", "btn-popover-menu-item"): _LocationControl(
                "btn-popover-menu-item",
                name="ページへ移動する",
            ),
            ("位置に移動", "btn-popover-menu-item"): _LocationControl(
                "btn-popover-menu-item",
                name="位置に移動",
            ),
            ("ページへ移動する", "modal-confirm"): _LocationControl(
                "modal-confirm",
                name="ページへ移動する",
            ),
            ("位置に移動", "modal-confirm"): _LocationControl(
                "modal-confirm",
                name="位置に移動",
            ),
        }
        self.clicked: list[str] = []
        self.keyboard_activated: list[str] = []
        self.stable_waits = 0

    def _control_by_id(self, automation_id: str, **_kwargs):
        return self.controls.get(automation_id)

    def _edit_by_id(self, automation_id: str, **_kwargs):
        return self.controls.get(automation_id)

    def _button_by_id(self, automation_id: str, **_kwargs):
        if automation_id == "modal-confirm":
            return next(
                (
                    control
                    for (_name, control_id), control in self.named_controls.items()
                    if control_id == automation_id
                ),
                None,
            )
        return self.controls.get(automation_id)

    def _control_by_name(
        self,
        name: str,
        *,
        automation_id: str,
        **_kwargs,
    ):
        return self.named_controls.get((name, automation_id))

    def _click_control(self, control: _LocationControl) -> None:
        self.clicked.append(control.AutomationId)
        if control.AutomationId == "modal-confirm":
            self.controls.pop("go-to-page-input", None)

    def _click_relative_to_control(
        self,
        control: _LocationControl,
        *,
        x_offset: int,
        y_offset: int,
    ) -> bool:
        del x_offset, y_offset
        self.clicked.append(f"{control.AutomationId}:first-item")
        return True

    def _activate_control_with_keyboard(self, control: _LocationControl) -> None:
        self.keyboard_activated.append(control.AutomationId)
        if control.AutomationId == "modal-confirm":
            self.controls.pop("go-to-page-input", None)

    def _ensure_process_running(self) -> None:
        return None

    def wait_for_reader_stable(self) -> None:
        self.stable_waits += 1
