from types import SimpleNamespace

from capture_loop_models import CaptureProgress, build_capture_result
from capture_loop_policy import (
    PageChangeAction,
    capture_stopped_too_early,
    expected_count_reached,
    page_change_recovery_actions,
)


def test_first_transition_recovery_keeps_retry_then_opposite_order() -> None:
    assert page_change_recovery_actions(page=2, retry_limit=2) == (
        PageChangeAction.RETRY_SELECTED,
        PageChangeAction.RETRY_SELECTED,
        PageChangeAction.TRY_OPPOSITE,
    )


def test_later_transition_never_switches_direction() -> None:
    assert page_change_recovery_actions(page=3, retry_limit=2) == (
        PageChangeAction.RETRY_SELECTED,
        PageChangeAction.RETRY_SELECTED,
    )


def test_expected_count_policy_distinguishes_reached_and_early_stop() -> None:
    assert expected_count_reached(2, 2)
    assert not expected_count_reached(1, 2)
    assert not expected_count_reached(20, None)
    assert capture_stopped_too_early(1, 2)
    assert not capture_stopped_too_early(2, 2)
    assert not capture_stopped_too_early(0, None)


def test_capture_result_builder_preserves_manifest_contract() -> None:
    config = SimpleNamespace(
        EXPECTED_PAGES=2,
        PAGE_CHANGE_KEY="left",
        CAPTURE_SPREAD=True,
        CROP_X1=10,
        CROP_Y1=20,
        CROP_X2=1010,
        CROP_Y2=720,
        TIMEOUT_SEC=5,
        PAGE_CHANGE_RETRY_COUNT=1,
    )
    progress = CaptureProgress(
        turn_commands=3,
        retry_commands=1,
        opposite_direction_commands=0,
        unchanged_observation_windows=2,
    )

    result = build_capture_result(
        config=config,
        save_dir="images/book",
        captured_pages=2,
        reason="expected_screen_count_confirmed",
        image_size=(1000, 700),
        termination_windows=2,
        progress=progress,
    )

    assert result.report.to_manifest() == {
        "policy_version": "kindle-completeness-v1",
        "termination_reason": "expected_screen_count_confirmed",
        "end_of_book_proven": True,
        "captured_screens": 2,
        "expected_screens": 2,
        "direction": "left",
        "layout": "spread",
        "crop_bounds": (10, 20, 1010, 720),
        "image_size": (1000, 700),
        "last_saved_file": "002.png",
        "unchanged_observation_windows": 2,
        "termination_unchanged_windows": 2,
        "observation_timeout_seconds": 5.0,
        "retry_limit": 1,
        "turn_commands": 3,
        "successful_transitions": 1,
        "retry_commands": 1,
        "opposite_direction_commands": 0,
    }
