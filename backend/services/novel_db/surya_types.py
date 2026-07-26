"""Surya OCRの公開データ型とworker session policy。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class SuryaBlock:
    label: str
    bbox: tuple[float, float, float, float]
    text: str


@dataclass(frozen=True)
class SuryaLayoutBlock:
    label: str
    bbox: tuple[float, float, float, float]
    count: int


@dataclass(frozen=True)
class SuryaPageResult:
    full_text: str
    raw_output: str
    blocks: list[SuryaBlock]
    state: str
    quality_flags: list[str]
    ink_coverage: float | None
    attempt_count: int
    error_message: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.full_text)


@dataclass
class OcrSessionPolicy:
    """worker所有の推論serverを交換する条件を判定する。"""

    max_pages: int
    consecutive_failure_limit: int
    failure_window: int
    failure_rate: float
    pages_processed: int = 0
    consecutive_failures: int = 0

    def __post_init__(self) -> None:
        self._recent_failures: deque[bool] = deque(maxlen=self.failure_window)

    def record(self, failed: bool) -> str | None:
        self.pages_processed += 1
        self.consecutive_failures = self.consecutive_failures + 1 if failed else 0
        self._recent_failures.append(failed)
        if self.consecutive_failures >= self.consecutive_failure_limit:
            return "consecutive_surya_failures"
        if (
            len(self._recent_failures) == self.failure_window
            and sum(self._recent_failures) / self.failure_window >= self.failure_rate
        ):
            return "surya_failure_rate"
        if self.pages_processed >= self.max_pages:
            return "page_limit"
        return None
