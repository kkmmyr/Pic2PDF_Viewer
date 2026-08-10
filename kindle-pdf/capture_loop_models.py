from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, dataclass
from typing import Protocol


class CaptureReportConfig(Protocol):
    EXPECTED_PAGES: int | None
    PAGE_CHANGE_KEY: str
    CROP_X1: int
    CROP_Y1: int
    CROP_X2: int
    CROP_Y2: int
    TIMEOUT_SEC: float
    PAGE_CHANGE_RETRY_COUNT: int


@dataclass(frozen=True)
class CaptureReport:
    policy_version: str
    termination_reason: str
    end_of_book_proven: bool
    captured_screens: int
    expected_screens: int | None
    direction: str
    layout: str
    crop_bounds: tuple[int, int, int, int]
    image_size: tuple[int, int]
    last_saved_file: str
    unchanged_observation_windows: int
    termination_unchanged_windows: int
    observation_timeout_seconds: float
    retry_limit: int
    turn_commands: int
    successful_transitions: int
    retry_commands: int
    opposite_direction_commands: int

    def to_manifest(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CaptureResult:
    captured_screens: int
    image_dir: str
    report: CaptureReport

    def __iter__(self) -> Iterator[int | str]:
        """既存の ``count, dir = capture_loop()`` 呼び出しを維持する。"""
        yield self.captured_screens
        yield self.image_dir


@dataclass
class CaptureProgress:
    turn_commands: int = 0
    retry_commands: int = 0
    opposite_direction_commands: int = 0
    unchanged_observation_windows: int = 0


def build_capture_result(
    *,
    config: CaptureReportConfig,
    save_dir: str,
    captured_pages: int,
    reason: str,
    image_size: tuple[int, int],
    termination_windows: int,
    progress: CaptureProgress,
) -> CaptureResult:
    report = CaptureReport(
        policy_version="kindle-completeness-v1",
        termination_reason=reason,
        end_of_book_proven=True,
        captured_screens=captured_pages,
        expected_screens=config.EXPECTED_PAGES,
        direction=config.PAGE_CHANGE_KEY,
        layout="spread" if getattr(config, "CAPTURE_SPREAD", False) else "single",
        crop_bounds=(
            int(config.CROP_X1),
            int(config.CROP_Y1),
            int(config.CROP_X2),
            int(config.CROP_Y2),
        ),
        image_size=image_size,
        last_saved_file=f"{captured_pages:03d}.png",
        unchanged_observation_windows=progress.unchanged_observation_windows,
        termination_unchanged_windows=termination_windows,
        observation_timeout_seconds=float(config.TIMEOUT_SEC),
        retry_limit=int(config.PAGE_CHANGE_RETRY_COUNT),
        turn_commands=progress.turn_commands,
        successful_transitions=max(0, captured_pages - 1),
        retry_commands=progress.retry_commands,
        opposite_direction_commands=progress.opposite_direction_commands,
    )
    return CaptureResult(captured_pages, save_dir, report)
