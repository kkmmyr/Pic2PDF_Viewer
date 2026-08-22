from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import kindle_app_controller as controller_module
import kindle_controller.window as window_module
from kindle_app_controller import (
    BookCandidate,
    BookIdentity,
    ControllerConfig,
    KindleAppController,
    KindleControllerError,
    candidate_matches_identity,
    select_verified_candidate,
    visual_frames_differ,
)
from kindle_platform import COMError


def _identity(**overrides) -> BookIdentity:
    values = {
        "asin": "B012345678",
        "title": "十三歳の誕生日、皇后になりました。 1",
        "title_normalized": "十三歳の誕生日、皇后になりました。1",
        "authors": ("石田リンネ",),
        "series_name": "十三歳の誕生日、皇后になりました。",
        "volume_number": 1.0,
        "volume_label": "1",
    }
    values.update(overrides)
    return BookIdentity(**values)


def test_asin_exact_match_has_priority() -> None:
    candidate = BookCandidate(
        asin="B012345678",
        title="アクセシブル名が正式タイトルと異なる",
    )

    assert candidate_matches_identity(_identity(), candidate)


def test_asin_mismatch_is_rejected_even_when_title_matches() -> None:
    candidate = BookCandidate(
        asin="B999999999",
        title="十三歳の誕生日、皇后になりました。1",
        authors=("石田リンネ",),
    )

    assert not candidate_matches_identity(_identity(), candidate)


def test_normalized_title_and_author_match_without_asin() -> None:
    candidate = BookCandidate(
        asin=None,
        title="十三歳の誕生日、皇后になりました。１",
        authors=("石田リンネ",),
    )

    assert candidate_matches_identity(_identity(), candidate)


def test_series_and_volume_match_without_author() -> None:
    candidate = BookCandidate(
        asin=None,
        title="十三歳の誕生日、皇后になりました。1",
        series_name="十三歳の誕生日、皇后になりました。",
        volume_number=1.0,
    )

    assert candidate_matches_identity(_identity(), candidate)


def test_title_only_is_not_enough_without_asin() -> None:
    candidate = BookCandidate(
        asin=None,
        title="十三歳の誕生日、皇后になりました。1",
    )

    assert not candidate_matches_identity(_identity(), candidate)


def test_candidate_not_found_and_ambiguous_have_distinct_codes() -> None:
    with pytest.raises(KindleControllerError) as missing:
        select_verified_candidate(_identity(), [])
    assert missing.value.error_code == "book_not_found"

    candidates = [
        BookCandidate(asin="B012345678", title="候補1"),
        BookCandidate(asin="B012345678", title="候補2"),
    ]
    with pytest.raises(KindleControllerError) as ambiguous:
        select_verified_candidate(_identity(), candidates)
    assert ambiguous.value.error_code == "book_match_ambiguous"


def test_visual_frames_differ_detects_page_change() -> None:
    white = Image.new("RGB", (200, 300), "white")
    same_white = Image.new("RGB", (200, 300), "white")
    black = Image.new("RGB", (200, 300), "black")

    assert not visual_frames_differ(white, same_white)
    assert visual_frames_differ(white, black)


def test_control_lookup_treats_transient_com_error_as_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _TransientControl:
        def Exists(self, *_args) -> bool:
            raise COMError(
                -2147220991,
                "event subscriber unavailable",
                (None, None, None, 0, None),
            )

    controller = KindleAppController()
    controller.window = object()
    monkeypatch.setattr(
        controller_module.auto,
        "Control",
        lambda **_kwargs: _TransientControl(),
    )

    assert controller._control_by_id("backButton", timeout=0.1) is None


def test_foreground_activation_attaches_threads_and_verifies_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _User32:
        foreground = 100
        attached: list[tuple[int, int, bool]] = []

        def GetForegroundWindow(self) -> int:
            return self.foreground

        def GetWindowThreadProcessId(self, handle, _process_id) -> int:
            return {100: 10, 200: 20}[handle]

        def AttachThreadInput(self, current, target, attach) -> int:
            self.attached.append((current, target, bool(attach)))
            return 1

        def ShowWindow(self, _handle, _command) -> int:
            return 1

        def BringWindowToTop(self, _handle) -> int:
            return 1

        def SetForegroundWindow(self, handle) -> int:
            self.foreground = handle
            return 1

    user32 = _User32()
    monkeypatch.setattr(
        window_module,
        "windll",
        SimpleNamespace(
            user32=user32,
            kernel32=SimpleNamespace(GetCurrentThreadId=lambda: 30),
        ),
    )
    controller = KindleAppController()

    controller._bring_to_foreground(200)

    assert user32.foreground == 200
    assert user32.attached == [
        (30, 10, True),
        (30, 20, True),
        (30, 20, False),
        (30, 10, False),
    ]


def test_foreground_activation_stops_when_windows_rejects_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = SimpleNamespace(
        GetForegroundWindow=lambda: 100,
        GetWindowThreadProcessId=lambda _handle, _process_id: 10,
        AttachThreadInput=lambda _current, _target, _attach: 1,
        ShowWindow=lambda _handle, _command: 1,
        BringWindowToTop=lambda _handle: 1,
        SetForegroundWindow=lambda _handle: 0,
    )
    monkeypatch.setattr(
        window_module,
        "windll",
        SimpleNamespace(
            user32=user32,
            kernel32=SimpleNamespace(GetCurrentThreadId=lambda: 30),
        ),
    )
    controller = KindleAppController(
        ControllerConfig(foreground_timeout_seconds=0),
    )

    with pytest.raises(KindleControllerError, match="前面化"):
        controller._bring_to_foreground(200)


def test_search_value_replaces_existing_full_width_input_with_exact_asin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ValuePattern:
        def __init__(self) -> None:
            self.Value = "Ｂ０１２３４５６７８Ｂ０１２３４５６７８"
            self.set_values: list[str] = []

        def SetValue(self, value: str) -> None:
            self.set_values.append(value)
            self.Value = value

    pattern = _ValuePattern()
    focused: list[bool] = []
    edit = SimpleNamespace(
        SetFocus=lambda: focused.append(True),
        GetValuePattern=lambda: pattern,
    )
    controller = KindleAppController()
    monkeypatch.setattr(controller, "_search_edit", lambda **_kwargs: edit)
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)

    controller._set_search_value("B012345678")

    assert focused == [True]
    assert pattern.set_values == ["B012345678"]
    assert pattern.Value == "B012345678"


def test_search_book_waits_for_delayed_asin_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = KindleAppController(ControllerConfig(screen_transition_seconds=0.0))
    identity = _identity()
    candidate = BookCandidate(
        asin=identity.asin,
        title=identity.title,
        card=object(),
    )
    candidate_reads: list[bool] = []
    monkeypatch.setattr(controller, "open_library", lambda: None)
    monkeypatch.setattr(controller, "_set_search_value", lambda _value: None)

    def _collect_candidates(_identity: BookIdentity) -> list[BookCandidate]:
        candidate_reads.append(True)
        return [] if len(candidate_reads) == 1 else [candidate]

    monkeypatch.setattr(controller, "collect_candidates", _collect_candidates)
    monkeypatch.setattr(controller_module.time, "sleep", lambda _seconds: None)

    assert controller.search_book(identity) == candidate
    assert len(candidate_reads) == 2


def test_control_center_rejects_invalid_bounds() -> None:
    control = SimpleNamespace(
        BoundingRectangle=SimpleNamespace(left=20, top=20, right=10, bottom=40)
    )

    with pytest.raises(KindleControllerError) as exc:
        KindleAppController._control_center(control)

    assert exc.value.error_code == "kindle_ui_unavailable"


def test_content_snapshot_requires_official_nonempty_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    content = (
        local_app_data
        / "Packages"
        / "AMZNKindle.AmazonKindleReadingApp_m1sc522ngdk36"
        / "LocalState"
        / "Classic"
        / "Content"
        / "B012345678_EBOK"
    )
    content.mkdir(parents=True)
    (content / "book.azw").write_bytes(b"azw")
    controller = KindleAppController()

    assert controller._content_snapshot("B012345678") is None

    (content / "book.voucher").write_bytes(b"voucher")
    snapshot = controller._content_snapshot("B012345678")

    assert snapshot is not None
    assert snapshot[:2] == (2, 10)
